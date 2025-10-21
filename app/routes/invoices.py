"""
Invoice Routes - All invoice operations
Uses services as controllers: routes -> services -> models
"""
import uuid
from flask import Blueprint, request, jsonify, current_app, g
from app import db
from app.models import Invoice, InvoiceLineItem, FileStorage, ProcessingJob, User
from app.utils.auth import require_auth, user_or_admin_required, admin_required, is_admin
from app.utils.audit import create_audit_log
from app.utils.response import generate_task_id, iso_timestamp, validate_uuid
from app.services.llm_service import get_llm_service
from app.services import async_processor
from app.services.async_processor import save_invoice_to_database
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.orm import joinedload

invoices_bp = Blueprint('invoices', __name__)


# === CRUD Operations ===

@invoices_bp.route('/', methods=['GET'])
@require_auth
@user_or_admin_required
def get_invoices():
    """Get all invoices with pagination and filtering"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)

        # Admin can view all or filter by specific user(s)
        view_all = request.args.get('view_all', 'false').lower() == 'true'
        filter_user_id = request.args.get('user_id')  # Legacy: single user
        filter_user_ids = request.args.get('user_ids')  # New: multiple users (comma-separated)

        # Build query with filters - use eager loading for user data
        query = Invoice.query.options(joinedload(Invoice.uploaded_by_user))

        # User filtering logic
        if is_admin():
            current_app.logger.info(
                f"[GET-INVOICES] Admin user - view_all={view_all}, "
                f"filter_user_id={filter_user_id}, "
                f"filter_user_ids={filter_user_ids}"
            )
            # Admin viewing all invoices with optional user filter
            if not view_all and not filter_user_id and not filter_user_ids:
                # Default: show invoices uploaded by this admin OR NULL
                current_app.logger.info(
                    "[GET-INVOICES] Applying default admin filter "
                    "(current user OR NULL)"
                )
                query = query.filter(
                    (Invoice.uploaded_by_user_id == g.current_user_id) |
                    (Invoice.uploaded_by_user_id.is_(None))
                )
            elif filter_user_ids:
                # Admin filtering by multiple users (new multi-select)
                # Supports special value 'null' or 'unassigned' to filter for NULL uploaded_by_user_id
                user_id_strings = [uid.strip() for uid in filter_user_ids.split(',') if uid.strip()]
                current_app.logger.info(f"[GET-INVOICES] Filtering by user_ids: {user_id_strings}")
                if user_id_strings:
                    # Check if filtering includes NULL/unassigned invoices
                    include_null = any(uid.lower() in ['null', 'unassigned'] for uid in user_id_strings)
                    # Get actual UUID strings (excluding 'null' and 'unassigned')
                    uuid_strings = [uid for uid in user_id_strings if uid.lower() not in ['null', 'unassigned']]

                    try:
                        filter_conditions = []

                        # Add user ID conditions
                        if uuid_strings:
                            user_id_list = [uuid.UUID(uid) for uid in uuid_strings]
                            current_app.logger.info(f"[GET-INVOICES] Converted to UUID list: {user_id_list}")
                            filter_conditions.append(Invoice.uploaded_by_user_id.in_(user_id_list))

                        # Add NULL condition if requested
                        if include_null:
                            current_app.logger.info("[GET-INVOICES] Including NULL/unassigned invoices")
                            filter_conditions.append(Invoice.uploaded_by_user_id.is_(None))

                        # Apply combined filter (OR condition)
                        if filter_conditions:
                            from sqlalchemy import or_
                            query = query.filter(or_(*filter_conditions))

                    except ValueError as e:
                        current_app.logger.error(f"Invalid user ID format in filter: {e}")
                        return jsonify({'error': 'Invalid user ID format'}), 400
            elif filter_user_id:
                # Admin filtering by single user (legacy support)
                try:
                    user_uuid = uuid.UUID(filter_user_id)
                    query = query.filter(Invoice.uploaded_by_user_id == user_uuid)
                except ValueError as e:
                    current_app.logger.error(f"Invalid user ID format: {e}")
                    return jsonify({'error': 'Invalid user ID format'}), 400
            # else: view_all is True, no user filter applied (shows ALL including NULLs)
        else:
            # Regular users can only see their own invoices
            query = query.filter(Invoice.uploaded_by_user_id == g.current_user_id)

        if request.args.get('customer_id'):
            query = query.filter(Invoice.customer_id == request.args.get('customer_id'))
        if request.args.get('salesperson_id'):
            query = query.filter(Invoice.salesperson_id == request.args.get('salesperson_id'))
        if request.args.get('status'):
            query = query.filter(Invoice.order_status == int(request.args.get('status')))
        if request.args.get('date_from'):
            query = query.filter(Invoice.invoice_date >= request.args.get('date_from'))
        if request.args.get('date_to'):
            query = query.filter(Invoice.invoice_date <= request.args.get('date_to'))

        invoices = query.order_by(Invoice.invoice_date.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        current_app.logger.info(
            f"[GET-INVOICES] Query returned {invoices.total} total "
            f"invoices, {len(invoices.items)} on this page"
        )

        # Build invoice list with user data (loaded via eager loading)
        invoices_with_users = []
        for invoice in invoices.items:
            invoice_dict = invoice.to_dict()
            # Add user info if available (already loaded via joinedload)
            if invoice.uploaded_by_user:
                invoice_dict['uploaded_by'] = {
                    'id': str(invoice.uploaded_by_user.id),
                    'name': invoice.uploaded_by_user.name,
                    'email': invoice.uploaded_by_user.email
                }
            else:
                invoice_dict['uploaded_by'] = None
            invoices_with_users.append(invoice_dict)

        return jsonify({
            'invoices': invoices_with_users,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': invoices.total,
                'pages': invoices.pages,
                'has_next': invoices.has_next,
                'has_prev': invoices.has_prev
            },
            'is_admin': is_admin(),
            'current_user_id': str(g.current_user_id)
        })

    except Exception as e:
        current_app.logger.error(f"Error getting invoices: {str(e)}")
        return jsonify({'error': str(e)}), 500


@invoices_bp.route('/<invoice_id>', methods=['GET'])
@require_auth
@user_or_admin_required
def get_invoice(invoice_id):
    """Get single invoice by ID with line items and blob URL"""
    try:
        uuid_id = uuid.UUID(invoice_id)
        # Use eager loading for user data
        invoice = Invoice.query.options(
            joinedload(Invoice.uploaded_by_user)
        ).filter_by(id=uuid_id).first()

        if not invoice:
            return jsonify({'error': 'Invoice not found'}), 404

        # Get invoice data
        invoice_data = invoice.to_dict()

        # Add user info if available (already loaded via joinedload)
        if invoice.uploaded_by_user:
            invoice_data['uploaded_by'] = {
                'id': str(invoice.uploaded_by_user.id),
                'name': invoice.uploaded_by_user.name,
                'email': invoice.uploaded_by_user.email
            }
        else:
            invoice_data['uploaded_by'] = None

        # Add line items
        invoice_data['line_items'] = [item.to_dict() for item in invoice.line_items]

        # Try to find the blob URL from FileStorage via ProcessingJob
        blob_url = None

        # Method 1: Query JSONB field for invoice_id
        try:
            processing_job = ProcessingJob.query.filter(
                ProcessingJob.result_data['invoice_id'].astext == str(invoice.id)
            ).first()
        except Exception as e:
            current_app.logger.debug(f"JSONB query failed: {str(e)}")
            processing_job = None

        # Method 2: Try to find by invoice filename
        if not processing_job and invoice.original_filename:
            try:
                processing_job = db.session.query(ProcessingJob).join(
                    FileStorage, ProcessingJob.file_storage_id == FileStorage.id
                ).filter(
                    FileStorage.file_name == invoice.original_filename
                ).first()
            except Exception as e:
                current_app.logger.debug(f"Filename query failed: {str(e)}")

        # Method 3: Search through all processing jobs (fallback)
        if not processing_job:
            all_jobs = ProcessingJob.query.filter(
                ProcessingJob.result_data.isnot(None)
            ).all()
            for job in all_jobs:
                if job.result_data and job.result_data.get('invoice_id') == str(invoice.id):
                    processing_job = job
                    break

        if processing_job and processing_job.file_storage_id:
            file_storage = FileStorage.query.get(processing_job.file_storage_id)
            if file_storage:
                blob_url = file_storage.blob_url

        invoice_data['blob_url'] = blob_url

        return jsonify(invoice_data)

    except ValueError:
        return jsonify({'error': 'Invalid invoice ID format'}), 400
    except Exception as e:
        current_app.logger.error(f"Error getting invoice: {str(e)}")
        import traceback
        current_app.logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@invoices_bp.route('/', methods=['POST'])
@require_auth
@user_or_admin_required
def create_invoice():
    """Create new invoice"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        # Create invoice
        invoice = Invoice(
            uploaded_by_user_id=g.current_user_id,
            customer_company=data.get('customer_company'),
            customer_address=data.get('customer_address'),
            invoice_number=data.get('invoice_number'),
            invoice_date=datetime.fromisoformat(data['invoice_date']),
            due_date=datetime.fromisoformat(data['due_date']),
            subtotal=Decimal(str(data.get('subtotal', 0))),
            tax_amount=Decimal(str(data.get('tax_amount', 0))),
            total_amount=Decimal(str(data.get('total_amount', 0))),
            order_status=data.get('order_status', 1)
        )

        # Save invoice with audit logging
        invoice.save()

        # Add line items with audit logging
        for item_data in data.get('line_items', []):
            line_item = InvoiceLineItem(
                invoice_id=invoice.id,
                description=item_data['description'],
                quantity=item_data['quantity'],
                unit_price=Decimal(str(item_data['unit_price'])),
                line_total=Decimal(str(item_data.get(
                    'line_total',
                    item_data['quantity'] * item_data['unit_price']
                )))
            )
            line_item.save()

        return jsonify({
            'success': True,
            'invoice': invoice.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to create invoice: {str(e)}")
        return jsonify({'error': str(e)}), 500


# === Processing Operations ===

@invoices_bp.route('/process', methods=['POST'])
@require_auth
@user_or_admin_required
def process_invoice():
    """
    Upload invoice from Vercel blob URL and process with streaming
    Uses: async_processor service -> llm_service -> websocket_manager
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        blob_url = data.get('blob_url')
        filename = data.get('filename')

        if not blob_url or not filename:
            return jsonify({
                'error': 'Missing required fields',
                'required': ['blob_url', 'filename']
            }), 400

        task_id = generate_task_id()

        # Processing options
        options = {
            'auto_save': data.get('auto_save', True),
            'confidence_threshold': data.get('confidence_threshold', 0.8),
            'user_id': g.current_user_id,
            'user_email': g.current_user_email
        }

        # Start async processing (service handles WebSocket streaming)
        task = async_processor.process_invoice_image_async.delay(blob_url, filename, task_id, options)

        current_app.logger.info(f"Started invoice processing: task_id={task_id}")

        return jsonify({
            'success': True,
            'task_id': task_id,
            'celery_task_id': task.id,
            'filename': filename,
            'status': 'queued',
            'message': 'Invoice processing started. Connect to WebSocket for real-time updates.',
            'websocket': {
                'room': f"task_{task_id}",
                'events': ['task_update']
            },
            'processing': options
        }), 202

    except Exception as e:
        current_app.logger.error(f"Invoice upload failed: {str(e)}")
        return jsonify({'error': str(e)}), 500


@invoices_bp.route('/process-batch', methods=['POST'])
@require_auth
def process_invoice_batch():
    """
    Process multiple invoices from Vercel blob URLs
    Creates FileStorage and ProcessingJob records, starts async processing
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        files = data.get('files', [])
        options = data.get('options', {})

        if not files:
            return jsonify({'error': 'No files provided'}), 400

        # Get user from Flask g object (set by @require_auth decorator)
        user_id = g.current_user_id
        current_app.logger.info(f"[PROCESS-BATCH] User ID from g.current_user_id: {user_id}")

        task_ids = []

        for file_info in files:
            blob_url = file_info.get('blob_url')
            filename = file_info.get('filename')
            file_size = file_info.get('file_size')
            mime_type = file_info.get('mime_type')

            if not blob_url or not filename:
                continue

            task_id = generate_task_id()

            # Create FileStorage record
            file_storage = FileStorage(
                user_id=user_id,
                file_name=filename,
                file_size=file_size or 0,
                mime_type=mime_type or 'application/octet-stream',
                blob_url=blob_url,
                blob_path=blob_url,  # Use blob_url as path for Vercel Blob
                upload_source='web'
            )
            db.session.add(file_storage)
            db.session.flush()

            # Audit log for file upload
            create_audit_log(
                table_name='file_storage',
                record_id=file_storage.id,
                action='CREATE',
                new_values=file_storage.to_dict(),
                reason=f'File uploaded for batch processing: {filename}'
            )

            # Create ProcessingJob record
            processing_job = ProcessingJob(
                id=task_id,
                user_id=user_id,
                file_storage_id=file_storage.id,
                job_type='invoice_extraction',
                status='pending',
                progress=0,
                auto_save=options.get('auto_save', True),
                cleanup=options.get('cleanup', True)
            )
            db.session.add(processing_job)
            db.session.flush()

            # Audit log for processing job creation
            create_audit_log(
                table_name='processing_jobs',
                record_id=processing_job.id,
                action='CREATE',
                new_values=processing_job.to_dict(),
                reason=f'Processing job created for file: {filename}'
            )

            task_ids.append(task_id)

        db.session.commit()

        # Start async processing for each task
        for task_id in task_ids:
            job = ProcessingJob.query.get(task_id)
            file_storage = FileStorage.query.get(job.file_storage_id)

            # Add user_id to options for notifications
            processing_options = {
                **options,
                'user_id': str(user_id),
                'user_email': getattr(g, 'current_user_email', None)
            }
            current_app.logger.info(
                f"[PROCESS-BATCH] Processing options for task {task_id}: "
                f"user_id={processing_options.get('user_id')}"
            )

            # Start async processing
            async_processor.process_invoice_image_async.delay(
                file_storage.blob_url,
                file_storage.file_name,
                str(task_id),
                processing_options
            )

        current_app.logger.info(f"Started batch processing: {len(task_ids)} tasks")

        return jsonify({
            'success': True,
            'task_ids': task_ids,
            'message': f'Processing {len(task_ids)} files'
        }), 202

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Batch processing failed: {str(e)}")
        return jsonify({'error': str(e)}), 500


@invoices_bp.route('/generate', methods=['POST'])
@require_auth
@admin_required
def generate_test_invoice():
    """
    Generate test invoice image (admin only)
    Uses: llm_service
    """
    try:
        data = request.get_json() or {}
        llm_service = get_llm_service()

        business_type = data.get('business_type', 'retail')
        complexity = data.get('complexity', 'detailed')
        company_name = data.get('company_name')

        # Validate business type
        supported_types = [bt['type'] for bt in llm_service.get_supported_business_types()]
        if business_type not in supported_types:
            return jsonify({
                'error': 'Invalid business type',
                'supported_types': supported_types
            }), 400

        # Generate invoice (service handles the logic)
        result = llm_service.generate_invoice_image(
            business_type=business_type,
            complexity=complexity,
            company_name=company_name
        )

        if not result.get('success'):
            return jsonify({
                'error': 'Invoice generation failed',
                'details': result.get('error')
            }), 500

        # Add admin context
        result['generated_by'] = {
            'admin_user_id': g.current_user_id,
            'admin_email': g.current_user_email,
            'generated_at': iso_timestamp()
        }

        return jsonify(result)

    except Exception as e:
        current_app.logger.error(f"Invoice generation failed: {str(e)}")
        return jsonify({'error': str(e)}), 500


@invoices_bp.route('/status/<task_id>', methods=['GET'])
@require_auth
@user_or_admin_required
def get_processing_status(task_id):
    """Get processing status for a task"""
    try:
        # Validate UUID
        if not validate_uuid(task_id):
            return jsonify({'error': 'Invalid task ID format'}), 400

        job = ProcessingJob.query.filter_by(id=task_id).first()
        if not job:
            return jsonify({'error': 'Task not found'}), 404

        response = {
            'task_id': task_id,
            'status': job.status,
            'progress': job.progress,
            'current_stage': job.current_stage,
            'created_at': job.created_at.isoformat() if job.created_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'error_message': job.error_message
        }

        if job.status == 'completed' and job.result_data:
            response['result'] = job.result_data

        if job.status in ['pending', 'running']:
            response['websocket'] = {
                'room': f"task_{task_id}",
                'events': ['task_update']
            }

        return jsonify(response)

    except Exception as e:
        current_app.logger.error(f"Error getting task status: {str(e)}")
        return jsonify({'error': str(e)}), 500


@invoices_bp.route('/approve/<task_id>', methods=['POST'])
@require_auth
@user_or_admin_required
def approve_and_save_invoice(task_id):
    """Approve and save invoice from processing job to database"""
    try:
        # Validate UUID
        if not validate_uuid(task_id):
            return jsonify({'error': 'Invalid task ID format'}), 400

        job = ProcessingJob.query.filter_by(id=task_id).first()
        if not job:
            return jsonify({'error': 'Task not found'}), 404

        # Check if job is completed successfully
        if job.status != 'completed':
            return jsonify({'error': 'Task is not completed'}), 400

        # Check if already saved
        if job.result_data and job.result_data.get('auto_saved'):
            return jsonify({
                'error': 'Invoice already saved',
                'invoice_id': job.result_data.get('invoice_id')
            }), 400

        # Get extraction result
        result_data = job.result_data
        if not result_data or not result_data.get('extraction_result'):
            return jsonify({'error': 'No extraction result found'}), 400

        extraction_result = result_data.get('extraction_result', {})
        structured_data = extraction_result.get('structured_data', {})
        confidence_score = extraction_result.get('confidence_score', 0.7)

        # Get filename from file storage
        file_storage = FileStorage.query.get(job.file_storage_id)
        filename = file_storage.file_name if file_storage else result_data.get('filename', 'unknown')

        # Attempt to save to database
        try:
            user_id = g.current_user_id
            invoice_id = save_invoice_to_database(structured_data, filename, confidence_score, user_id)

            # Update job result to mark as saved
            updated_result_data = job.result_data.copy() if job.result_data else {}
            updated_result_data['auto_saved'] = True
            updated_result_data['invoice_id'] = invoice_id
            updated_result_data['approved_by'] = str(g.current_user_id)
            updated_result_data['approved_at'] = datetime.now(timezone.utc).isoformat()

            # Update the job with the new result_data
            job.result_data = updated_result_data

            # Mark the JSONB field as modified so SQLAlchemy detects the change
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(job, 'result_data')

            db.session.commit()

            current_app.logger.info(f"Invoice approved and saved: task_id={task_id}, invoice_id={invoice_id}")

            return jsonify({
                'success': True,
                'invoice_id': invoice_id,
                'message': 'Invoice approved and saved successfully',
                'job': job.to_dict()  # Return updated job data
            }), 200

        except ValueError as e:
            # Handle duplicate invoice detection
            error_msg = str(e)
            if "already exists" in error_msg.lower() or "duplicate" in error_msg.lower():
                # This is a duplicate - mark job as complete with note
                current_app.logger.warning(f"Duplicate invoice detected during approval: {error_msg}")

                # Update result_data with duplicate information
                updated_result_data = job.result_data.copy() if job.result_data else {}
                updated_result_data['duplicate_detected'] = True
                updated_result_data['duplicate_error'] = error_msg
                updated_result_data['approved_by'] = str(g.current_user_id)
                updated_result_data['approved_at'] = datetime.now(timezone.utc).isoformat()
                updated_result_data['db_insert_skipped'] = True
                updated_result_data['skip_reason'] = 'Invoice is a duplicate of existing record'

                # Update the job with the new result_data
                job.result_data = updated_result_data

                # Mark the JSONB field as modified so SQLAlchemy detects the change
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(job, 'result_data')

                db.session.commit()

                return jsonify({
                    'success': False,
                    'duplicate_detected': True,
                    'message': f'Cannot insert this invoice - it is a duplicate. {error_msg}',
                    'details': 'Job marked as complete. No database insert was made.',
                    'job': job.to_dict()  # Return updated job data
                }), 409  # 409 Conflict status code
            else:
                # Other validation error - re-raise
                raise

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Failed to approve invoice: {str(e)}")
        return jsonify({'error': str(e)}), 500


@invoices_bp.route('/supported-types', methods=['GET'])
def get_supported_types():
    """Get supported business types and formats (public endpoint)"""
    try:
        llm_service = get_llm_service()

        return jsonify({
            'business_types': llm_service.get_supported_business_types(),
            'complexity_levels': [
                {'level': 'simple', 'description': '3-5 line items, basic formatting'},
                {'level': 'detailed', 'description': '6-10 line items, detailed formatting'},
                {'level': 'complex', 'description': '10+ line items, complex formatting with discounts'}
            ],
            'supported_formats': llm_service.get_supported_image_formats()
        })

    except Exception as e:
        current_app.logger.error(f"Error getting supported types: {str(e)}")
        return jsonify({'error': str(e)}), 500


@invoices_bp.route('/<invoice_id>', methods=['PUT'])
@require_auth
@user_or_admin_required
def update_invoice(invoice_id):
    """Update invoice and line items"""
    try:
        uuid_id = uuid.UUID(invoice_id)
        invoice = Invoice.query.filter_by(id=uuid_id).first()

        if not invoice:
            return jsonify({'error': 'Invoice not found'}), 404

        # Check permissions: user can update their own invoices, admin can update any
        if not is_admin() and invoice.uploaded_by_user_id != g.current_user_id:
            return jsonify({'error': 'Unauthorized to update this invoice'}), 403

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400

        # Update invoice fields
        updatable_fields = [
            'invoice_number', 'invoice_date', 'due_date', 'ship_date',
            'customer_id', 'salesperson_id', 'territory_id', 'account_number',
            'po_number', 'ship_via', 'fob', 'terms', 'subtotal', 'tax_rate',
            'tax_amount', 'freight', 'shipping_handling', 'other_charges',
            'total_amount', 'order_status', 'payment_status', 'special_instructions',
            'notes'
        ]

        for field in updatable_fields:
            if field in data:
                value = data[field]
                # Convert date strings to date objects
                if field in ['invoice_date', 'due_date', 'ship_date'] and value:
                    if isinstance(value, str):
                        value = datetime.fromisoformat(value.replace('Z', '+00:00')).date()
                # Convert decimal strings to Decimal
                elif field in [
                    'subtotal', 'tax_rate', 'tax_amount', 'freight',
                    'shipping_handling', 'other_charges', 'total_amount'
                ] and value is not None:
                    value = Decimal(str(value))
                setattr(invoice, field, value)

        # Update line items if provided
        if 'line_items' in data:
            # Delete existing line items
            for item in invoice.line_items:
                db.session.delete(item)

            # Add new line items
            for item_data in data['line_items']:
                line_item = InvoiceLineItem(
                    invoice_id=invoice.id,
                    line_number=item_data.get('line_number', 0),
                    item_number=item_data.get('item_number'),
                    description=item_data['description'],
                    quantity=item_data['quantity'],
                    unit_price=Decimal(str(item_data['unit_price'])),
                    unit_price_discount=Decimal(
                        str(item_data.get('unit_price_discount', 0))
                    ),
                    line_total=Decimal(str(item_data.get(
                        'line_total',
                        item_data['quantity'] * item_data['unit_price']
                    ))),
                    unit_of_measure=item_data.get('unit_of_measure')
                )
                db.session.add(line_item)

        db.session.commit()

        # Return updated invoice with line items
        invoice_data = invoice.to_dict()
        invoice_data['line_items'] = [item.to_dict() for item in invoice.line_items]

        return jsonify({
            'success': True,
            'invoice': invoice_data,
            'message': 'Invoice updated successfully'
        })

    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': f'Invalid data format: {str(e)}'}), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating invoice: {str(e)}")
        return jsonify({'error': str(e)}), 500


@invoices_bp.route('/users', methods=['GET'])
@require_auth
@admin_required
def get_invoice_users():
    """Get all users who have uploaded invoices (admin only)"""
    try:
        # Get distinct users who have uploaded invoices
        users = db.session.query(User).join(
            Invoice, Invoice.uploaded_by_user_id == User.id
        ).distinct().all()

        # Check if there are any unassigned invoices
        unassigned_count = db.session.query(Invoice).filter(
            Invoice.uploaded_by_user_id.is_(None)
        ).count()

        user_list = [
            {
                'id': str(user.id),
                'name': user.name,
                'email': user.email
            }
            for user in users
        ]

        # Add "Unassigned" option if there are any unassigned invoices
        if unassigned_count > 0:
            user_list.insert(0, {
                'id': 'null',
                'name': f'Unassigned ({unassigned_count})',
                'email': None
            })

        return jsonify({
            'users': user_list
        })

    except Exception as e:
        current_app.logger.error(f"Error getting invoice users: {str(e)}")
        return jsonify({'error': str(e)}), 500
