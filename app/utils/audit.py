"""
Audit logging utilities for comprehensive database operation tracking
"""
from flask import g, has_request_context
from app import db
from app.models.audit_log import AuditLog
from typing import Optional, Dict, Any


def create_audit_log(
    table_name: str,
    record_id: Any,
    action: str,
    old_values: Optional[Dict] = None,
    new_values: Optional[Dict] = None,
    user_email: Optional[str] = None,
    reason: Optional[str] = None
):
    """
    Create an audit log entry for any database operation.

    Args:
        table_name: Name of the table being modified
        record_id: ID of the record being modified (can be UUID or string)
        action: Type of action (CREATE, UPDATE, DELETE, BULK_CREATE, etc.)
        old_values: Dictionary of old values (for UPDATE/DELETE)
        new_values: Dictionary of new values (for CREATE/UPDATE)
        user_email: Email of user performing action (auto-detected if not provided)
        reason: Optional reason for the change

    Example:
        # For CREATE
        create_audit_log(
            table_name='invoices',
            record_id=invoice.id,
            action='CREATE',
            new_values=invoice.to_dict(),
            user_email=g.current_user_email,
            reason='Admin manual creation'
        )

        # For UPDATE
        create_audit_log(
            table_name='users',
            record_id=user.id,
            action='UPDATE',
            old_values=old_user_dict,
            new_values=user.to_dict(),
            reason='Role change'
        )

        # For DELETE
        create_audit_log(
            table_name='products',
            record_id=product.id,
            action='DELETE',
            old_values=product.to_dict()
        )
    """
    try:
        # Get user email from request context if not provided
        if not user_email and has_request_context():
            user_email = getattr(g, 'current_user_email', None)

        # Calculate changed fields for updates
        changed_fields = []
        if action == 'UPDATE' and old_values and new_values:
            changed_fields = [
                field for field in new_values.keys()
                if old_values.get(field) != new_values.get(field)
            ]

        # Create audit log entry
        audit_entry = AuditLog(
            table_name=table_name,
            record_id=record_id,
            action=action,
            old_values=old_values,
            new_values=new_values,
            changed_fields=changed_fields,
            changed_by=user_email or 'system',
            change_reason=reason
        )

        # Add to session (caller should handle commit)
        db.session.add(audit_entry)

    except Exception as e:
        # Log error but don't fail the main operation
        if has_request_context():
            from flask import current_app
            current_app.logger.error(f"Failed to create audit log: {e}")
        else:
            print(f"Audit logging error: {e}")


def audit_bulk_operation(
    table_name: str,
    action: str,
    record_count: int,
    summary: Optional[Dict] = None,
    user_email: Optional[str] = None,
    reason: Optional[str] = None
):
    """
    Create an audit log entry for bulk operations.

    Args:
        table_name: Name of the table being modified
        action: Type of action (BULK_CREATE, BULK_UPDATE, BULK_DELETE, BULK_IMPORT)
        record_count: Number of records affected
        summary: Optional dictionary with operation summary
        user_email: Email of user performing action
        reason: Optional reason for the bulk operation

    Example:
        audit_bulk_operation(
            table_name='products',
            action='BULK_IMPORT',
            record_count=150,
            summary={'source': 'Excel import', 'filename': 'products.xlsx'},
            reason='Monthly product catalog update'
        )
    """
    try:
        if not user_email and has_request_context():
            user_email = getattr(g, 'current_user_email', None)

        new_values = {
            'bulk_operation': True,
            'records_affected': record_count,
            **(summary or {})
        }

        audit_entry = AuditLog(
            table_name=table_name,
            record_id=None,  # No specific record for bulk ops
            action=action,
            old_values=None,
            new_values=new_values,
            changed_fields=[],
            changed_by=user_email or 'system',
            change_reason=reason or f'Bulk operation: {record_count} records'
        )

        db.session.add(audit_entry)

    except Exception as e:
        if has_request_context():
            from flask import current_app
            current_app.logger.error(f"Failed to create bulk audit log: {e}")
        else:
            print(f"Bulk audit logging error: {e}")


def audit_before_after(
    table_name: str,
    record_id: Any,
    old_instance: Any,
    new_instance: Any,
    action: str = 'UPDATE',
    user_email: Optional[str] = None,
    reason: Optional[str] = None
):
    """
    Create audit log from before/after model instances.

    Useful when you have the old and new model instances.

    Args:
        table_name: Name of the table
        record_id: ID of the record
        old_instance: Old model instance (or dict)
        new_instance: New model instance (or dict)
        action: Type of action (default: UPDATE)
        user_email: Email of user performing action
        reason: Optional reason for the change

    Example:
        old_invoice = Invoice.query.get(invoice_id)
        # ... make changes to invoice ...
        audit_before_after(
            table_name='invoices',
            record_id=invoice.id,
            old_instance=old_invoice,
            new_instance=invoice,
            reason='Status update'
        )
    """
    try:
        # Convert instances to dicts if they have to_dict method
        old_values = old_instance.to_dict() if hasattr(old_instance, 'to_dict') else old_instance
        new_values = new_instance.to_dict() if hasattr(new_instance, 'to_dict') else new_instance

        create_audit_log(
            table_name=table_name,
            record_id=record_id,
            action=action,
            old_values=old_values,
            new_values=new_values,
            user_email=user_email,
            reason=reason
        )

    except Exception as e:
        if has_request_context():
            from flask import current_app
            current_app.logger.error(f"Failed to create before/after audit log: {e}")
        else:
            print(f"Before/after audit logging error: {e}")


def get_current_user_email() -> Optional[str]:
    """Get current user email from request context."""
    if has_request_context():
        return getattr(g, 'current_user_email', None)
    return None

