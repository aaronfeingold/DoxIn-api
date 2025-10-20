"""
Unified Async Processor - Handles all background LLM tasks
Replaces: background_processor.py (and removes document_processor.py dependency)
"""
import os
import uuid
import time
import tempfile
import requests
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from celery import Celery
from flask import current_app
from app.services.llm_service import get_llm_service
from app.services.websocket_manager import get_websocket_manager
from app.services.redis_event_bridge import get_redis_event_bridge
from app.models import Invoice, InvoiceLineItem
from app import db
from decimal import Decimal


# Initialize Celery app (works standalone or with Flask)
celery_app = Celery(
    'case_study',
    broker=os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
    backend=os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

# Flask app for worker context (lazy initialization)
_flask_app = None

def get_flask_app():
    """Get or create Flask app for worker context"""
    global _flask_app
    if _flask_app is None:
        from app import create_app
        _flask_app = create_app()
    return _flask_app


def send_progress_update(task_id: str, progress: int, message: str, stage: str = None):
    """Send progress update via Redis (works from Celery worker)"""
    bridge = get_redis_event_bridge()
    bridge.publish_task_update(task_id, {
        'type': 'progress',
        'progress': progress,
        'message': message,
        'stage': stage,
        'timestamp': int(time.time() * 1000)
    })


def send_task_complete_update(task_id: str, result: Dict[str, Any], user_id: str = None):
    """Send task completion update via Redis (works from Celery worker)"""
    bridge = get_redis_event_bridge()
    bridge.publish_task_update(task_id, {
        'type': 'complete',
        'result': result,
        'timestamp': int(time.time() * 1000)
    })

    # Also send user notification
    if user_id:
        bridge.publish_user_notification(user_id, {
            'type': 'job_completed',
            'task_id': task_id,
            'status': 'completed',
            'filename': result.get('filename'),
            'timestamp': int(time.time() * 1000)
        })


def send_task_error_update(task_id: str, error: str, user_id: str = None, filename: str = None):
    """Send task error update via Redis (works from Celery worker)"""
    bridge = get_redis_event_bridge()
    bridge.publish_task_update(task_id, {
        'type': 'error',
        'error': error,
        'timestamp': int(time.time() * 1000)
    })

    # Also send user notification
    if user_id:
        bridge.publish_user_notification(user_id, {
            'type': 'job_failed',
            'task_id': task_id,
            'status': 'failed',
            'error': error,
            'filename': filename,
            'timestamp': int(time.time() * 1000)
        })


def send_stage_update(task_id: str, stage: str, description: str):
    """Send stage start update via Redis (works from Celery worker)"""
    bridge = get_redis_event_bridge()
    bridge.publish_task_update(task_id, {
        'type': 'stage_start',
        'stage': stage,
        'description': description,
        'timestamp': int(time.time() * 1000)
    })


def make_celery(app):
    """Update Celery instance with Flask app context"""
    celery_app.conf.update(
        broker_url=app.config.get('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
        result_backend=app.config.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')
    )

    class ContextTask(celery_app.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app.Task = ContextTask
    return celery_app


def init_celery(app) -> Celery:
    """Initialize Celery with Flask app"""
    return make_celery(app)


# Task implementations with decorators
@celery_app.task(bind=True, name='process_invoice_image_async')
def process_invoice_image_async(self, image_data_or_url: str, filename: str, task_id: str, options: Dict[str, Any] = None):
    """
    Process invoice image asynchronously with real-time updates
    Handles both base64 image data and blob URLs
    """
    app = get_flask_app()
    with app.app_context():
        return _process_invoice_image_async_impl(self, image_data_or_url, filename, task_id, options)

def _process_invoice_image_async_impl(self, image_data_or_url: str, filename: str, task_id: str, options: Dict[str, Any] = None):
    """Implementation of invoice image processing"""
    llm_service = get_llm_service()
    options = options or {}

    try:
        from app.models import ProcessingJob

        # Update ProcessingJob status to running
        job = ProcessingJob.query.get(task_id)
        if job:
            job.status = 'running'
            job.current_stage = 'fetch'
            db.session.commit()

        # Stage 1: Get image data
        send_stage_update(task_id, 'fetch', 'Preparing image for processing...')

        if image_data_or_url.startswith('http'):
            # Download from URL
            send_progress_update(task_id, 10, 'Downloading image...', 'fetch')

            response = requests.get(image_data_or_url, timeout=30)
            response.raise_for_status()
            image_data = response.content
        else:
            # Assume it's base64 or binary data
            if isinstance(image_data_or_url, str):
                import base64
                image_data = base64.b64decode(image_data_or_url)
            else:
                image_data = image_data_or_url

        send_progress_update(task_id, 20, f'Image ready ({len(image_data)} bytes)', 'fetch')

        # Stage 2: LLM Processing
        send_stage_update(task_id, 'llm_extraction', 'Analyzing invoice with AI...')

        # Progress callback for LLM processing
        def progress_callback(progress, message):
            send_progress_update(task_id, 30 + int(progress * 50), message, 'llm_extraction')

        # Extract invoice data using LLM
        extraction_result = llm_service.extract_invoice_from_image(
            image_data, filename, progress_callback=progress_callback
        )

        if not extraction_result.get('success'):
            raise Exception(f"LLM extraction failed: {extraction_result.get('error')}")

        send_progress_update(task_id, 80, f'Extraction complete (confidence: {extraction_result.get("confidence_score", 0):.0%})', 'llm_extraction')

        # Stage 3: Data Validation
        structured_data = extraction_result.get('structured_data', {})
        confidence_score = extraction_result.get('confidence_score', 0.7)

        send_stage_update(task_id, 'validation', 'Validating extracted data...')
        send_progress_update(task_id, 85, 'Checking data quality...', 'validation')

        # Basic validation
        validation_errors = []
        required_fields = ['invoice_number', 'total_amount']
        for field in required_fields:
            if not structured_data.get(field):
                validation_errors.append(f"Missing required field: {field}")

        requires_review = len(validation_errors) > 0 or confidence_score < options.get('confidence_threshold', 0.8)

        send_progress_update(task_id, 90, 'Validation complete', 'validation')

        # Stage 4: Auto-save (if enabled and high confidence)
        invoice_id = None
        auto_saved = False
        duplicate_detected = False
        save_skip_reason = None

        if not options.get('auto_save', False):
            save_skip_reason = "Auto-save is disabled"
        elif requires_review:
            save_skip_reason = "Invoice requires human review due to low confidence or validation errors"

        if options.get('auto_save', False) and not requires_review:
            send_stage_update(task_id, 'save', 'Saving invoice to database...')
            send_progress_update(task_id, 90, 'Creating invoice record...', 'save')

            try:
                user_id = options.get('user_id')
                current_app.logger.info(f"[ASYNC-PROCESSOR] Saving invoice - user_id from options: {user_id}")
                invoice_id = save_invoice_to_database(structured_data, filename, confidence_score, user_id)
                auto_saved = True

                send_progress_update(task_id, 95, 'Invoice saved successfully', 'save')

            except ValueError as e:
                # Duplicate invoice detected
                error_msg = str(e)
                if "already exists" in error_msg.lower() or "duplicate" in error_msg.lower() or "already been processed" in error_msg.lower():
                    duplicate_detected = True
                    save_skip_reason = error_msg
                    current_app.logger.warning(f"Duplicate invoice detected: {error_msg}")
                    validation_errors.append(f"Duplicate detected: {error_msg}")
                else:
                    current_app.logger.error(f"Auto-save failed: {error_msg}")
                    save_skip_reason = error_msg
                    validation_errors.append(f"Auto-save failed: {error_msg}")
            except Exception as e:
                current_app.logger.error(f"Auto-save failed: {str(e)}")
                save_skip_reason = str(e)
                validation_errors.append(f"Auto-save failed: {str(e)}")

        # Stage 5: Complete
        final_result = {
            'task_id': task_id,
            'filename': filename,
            'extraction_result': extraction_result,
            'structured_data': structured_data,
            'confidence_score': confidence_score,
            'validation_errors': validation_errors,
            'requires_review': requires_review,
            'auto_saved': auto_saved,
            'duplicate_detected': duplicate_detected,
            'save_skip_reason': save_skip_reason,
            'invoice_id': invoice_id,
            'completed_at': int(time.time() * 1000)
        }

        # Update ProcessingJob to completed
        job = ProcessingJob.query.get(task_id)
        if job:
            job.status = 'completed'
            job.progress = 100
            job.completed_at = datetime.now(timezone.utc)
            job.result_data = final_result
            db.session.commit()

        send_progress_update(task_id, 100, 'Processing complete!', 'complete')
        user_id = options.get('user_id') if options else None
        send_task_complete_update(task_id, final_result, user_id=user_id)

        return final_result

    except Exception as e:
        error_message = str(e)
        current_app.logger.error(f"Async invoice processing failed: {error_message}")

        # Update ProcessingJob to failed
        try:
            job = ProcessingJob.query.get(task_id)
            if job:
                job.status = 'failed'
                job.error_message = error_message
                db.session.commit()
        except:
            pass

        user_id = options.get('user_id') if options else None
        send_task_error_update(task_id, error_message, user_id=user_id, filename=filename)

        return {
            'task_id': task_id,
            'success': False,
            'error': error_message
        }


@celery_app.task(bind=True, name='process_text_analysis_async')
def process_text_analysis_async(self, text_content: str, analysis_type: str, task_id: str, options: Dict[str, Any] = None):
    """Process text analysis asynchronously"""
    app = get_flask_app()
    with app.app_context():
        return _process_text_analysis_async_impl(self, text_content, analysis_type, task_id, options)

def _process_text_analysis_async_impl(self, text_content: str, analysis_type: str, task_id: str, options: Dict[str, Any] = None):
    """Implementation of text analysis processing"""
    llm_service = get_llm_service()
    options = options or {}

    try:
        send_stage_update(task_id, 'analysis', f'Starting {analysis_type} analysis...')

        # Progress callback
        def progress_callback(progress, message):
            send_progress_update(task_id, int(progress * 100), message, 'analysis')

        # Analyze with LLM
        analysis_result = llm_service.analyze_text(
            text_content, analysis_type, progress_callback=progress_callback
        )

        if not analysis_result.get('success'):
            raise Exception(f"Text analysis failed: {analysis_result.get('error')}")

        final_result = {
            'task_id': task_id,
            'analysis_type': analysis_type,
            'analysis_result': analysis_result,
            'completed_at': int(time.time() * 1000)
        }

        send_task_complete_update(task_id, final_result)

        return final_result

    except Exception as e:
        error_message = str(e)
        current_app.logger.error(f"Text analysis failed: {error_message}")

        send_task_error_update(task_id, error_message)

        return {
            'task_id': task_id,
            'success': False,
            'error': error_message
        }


@celery_app.task(bind=True, name='process_webhook_request_async')
def process_webhook_request_async(self, webhook_data: Dict[str, Any], task_id: str):
    """Process webhook requests asynchronously"""
    app = get_flask_app()
    with app.app_context():
        return _process_webhook_request_async_impl(self, webhook_data, task_id)

def _process_webhook_request_async_impl(self, webhook_data: Dict[str, Any], task_id: str):
    """Implementation of webhook request processing"""

    try:
        webhook_type = webhook_data.get('type', 'unknown')

        send_stage_update(task_id, 'webhook', f'Processing {webhook_type} webhook...')

        if webhook_type == 'invoice_uploaded':
            # Process as invoice
            blob_url = webhook_data.get('blob_url')
            filename = webhook_data.get('filename', 'webhook_invoice')
            options = {
                'auto_save': webhook_data.get('auto_save', True),
                'confidence_threshold': webhook_data.get('confidence_threshold', 0.8)
            }

            # Delegate to invoice processing task
            return process_invoice_image_async.delay(blob_url, filename, task_id, options)

        else:
            # Generic webhook processing
            result = {
                'task_id': task_id,
                'webhook_type': webhook_type,
                'webhook_data': webhook_data,
                'message': f'Webhook {webhook_type} processed',
                'completed_at': int(time.time() * 1000)
            }

            send_task_complete_update(task_id, result)

            return result

    except Exception as e:
        error_message = str(e)
        current_app.logger.error(f"Webhook processing failed: {error_message}")

        send_task_error_update(task_id, error_message)

        return {
            'task_id': task_id,
            'success': False,
            'error': error_message
        }


def save_invoice_to_database(structured_data: Dict[str, Any], filename: str, confidence_score: float, user_id: Optional[str] = None) -> str:
    """Save extracted invoice data to database"""
    try:
        invoice_number = structured_data.get('invoice_number')

        if not invoice_number:
            raise ValueError("Invoice number is required to save invoice")

        # Check if invoice with this invoice_number already exists
        existing_invoice = Invoice.query.filter_by(invoice_number=invoice_number).first()
        if existing_invoice:
            # Check if it's the exact same file being reprocessed
            if existing_invoice.original_filename == filename:
                current_app.logger.warning(
                    f"Invoice {invoice_number} from file '{filename}' was already processed with ID {existing_invoice.id}. "
                    "Skipping duplicate file upload."
                )
                raise ValueError(
                    f"This file '{filename}' has already been processed. "
                    f"Invoice #{invoice_number} exists in the system."
                )
            else:
                current_app.logger.warning(
                    f"Invoice number {invoice_number} already exists (ID: {existing_invoice.id}, "
                    f"original file: '{existing_invoice.original_filename}'). "
                    f"Cannot save duplicate from file '{filename}'."
                )
                raise ValueError(
                    f"Invoice #{invoice_number} already exists in the system "
                    f"(from file '{existing_invoice.original_filename}'). "
                    "Each invoice number must be unique."
                )

        # Generate a unique sales_order_id
        # Get the max existing sales_order_id and add 1
        max_sales_order = db.session.query(db.func.max(Invoice.sales_order_id)).scalar()
        sales_order_id = (max_sales_order or 0) + 1

        # Create invoice record
        # Handle user_id being either a string or UUID object
        if user_id:
            if isinstance(user_id, uuid.UUID):
                uploaded_by_user_id_value = user_id
            else:
                uploaded_by_user_id_value = uuid.UUID(user_id)
        else:
            uploaded_by_user_id_value = None
        current_app.logger.info(f"[SAVE-INVOICE] Creating invoice - user_id={user_id}, uploaded_by_user_id={uploaded_by_user_id_value}")
        invoice = Invoice(
            sales_order_id=sales_order_id,
            invoice_number=invoice_number,
            invoice_date=structured_data.get('invoice_date'),
            due_date=structured_data.get('due_date'),
            subtotal=Decimal(str(structured_data.get('subtotal', 0))),
            tax_amount=Decimal(str(structured_data.get('tax_amount', 0))),
            total_amount=Decimal(str(structured_data.get('total_amount', 0))),
            uploaded_by_user_id=uploaded_by_user_id_value,
            original_filename=filename,
            processed_by_llm=True,
            confidence_score=Decimal(str(confidence_score)),
            requires_review=confidence_score < 0.8
        )

        # Add bill_to information if available
        bill_to = structured_data.get('bill_to', {})
        if bill_to.get('company_name'):
            invoice.notes = f"Bill To: {bill_to.get('company_name')}"
            if bill_to.get('address'):
                invoice.notes += f", {bill_to.get('address')}"

        db.session.add(invoice)
        db.session.flush()  # Get the invoice ID

        # Add line items
        for i, item_data in enumerate(structured_data.get('line_items', [])):
            line_item = InvoiceLineItem(
                invoice_id=invoice.id,
                line_number=i + 1,
                description=item_data.get('description', ''),
                quantity=item_data.get('quantity', 1),
                unit_price=Decimal(str(item_data.get('unit_price', 0))),
                line_total=Decimal(str(item_data.get('line_total', 0)))
            )
            db.session.add(line_item)

        db.session.commit()
        return str(invoice.id)

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to save invoice: {str(e)}")
        raise
