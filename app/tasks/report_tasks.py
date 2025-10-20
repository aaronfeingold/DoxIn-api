"""
Celery tasks for asynchronous report generation
"""
from app.services.background_processor import celery_app
from app import db, create_app
from app.models.report import Report
from app.services.report_service import ReportService
from datetime import datetime
import traceback


@celery_app.task(bind=True, name='tasks.generate_report')
def generate_report_task(self, report_id):
    """
    Generate a report asynchronously

    Args:
        report_id: UUID of the Report record

    Returns:
        dict with status and results
    """
    # Create app context for database access
    app = create_app()

    with app.app_context():
        try:
            # Get report record
            report = db.session.query(Report).get(report_id)
            if not report:
                return {'status': 'failed', 'error': 'Report not found'}

            # Update status to processing
            report.status = 'processing'
            report.started_at = datetime.utcnow()
            db.session.commit()

            # Initialize report service
            service = ReportService(db.session)

            # Generate report based on type
            start_time = datetime.utcnow()

            if report.report_type == 'financial':
                result = service.generate_financial_report(report.parameters)
            elif report.report_type == 'sales':
                result = service.generate_sales_report(report.parameters)
            elif report.report_type == 'custom':
                result = service.generate_custom_report(report.parameters)
            else:
                raise ValueError(f"Unknown report type: {report.report_type}")

            # Calculate processing time
            end_time = datetime.utcnow()
            processing_time = (end_time - start_time).total_seconds()

            # Check for errors in result
            if 'error' in result:
                report.status = 'failed'
                report.error_message = result['error']
            else:
                # Update report with results
                report.status = 'completed'
                report.file_path = result['file_path']
                report.file_format = result.get('file_format', 'png')
                report.generated_at = end_time
                report.processing_time_seconds = int(processing_time)

                # Store metrics in parameters
                if 'metrics' in result:
                    if not report.parameters:
                        report.parameters = {}
                    report.parameters['result_metrics'] = result['metrics']

            report.completed_at = datetime.utcnow()
            db.session.commit()

            return {
                'status': report.status,
                'report_id': report_id,
                'file_path': report.file_path
            }

        except Exception as e:
            # Mark report as failed
            try:
                report = db.session.query(Report).get(report_id)
                if report:
                    report.status = 'failed'
                    report.error_message = str(e)
                    report.completed_at = datetime.utcnow()
                    db.session.commit()
            except:
                pass

            # Log the full error
            app.logger.error(f"Report generation failed for {report_id}: {str(e)}")
            app.logger.error(traceback.format_exc())

            return {
                'status': 'failed',
                'error': str(e),
                'report_id': report_id
            }


@celery_app.task(name='tasks.cleanup_old_reports')
def cleanup_old_reports_task(days=30):
    """
    Clean up old reports to save disk space

    Args:
        days: Delete reports older than this many days

    Returns:
        dict with number of reports deleted
    """
    app = create_app()

    with app.app_context():
        try:
            from datetime import timedelta
            import os
            from pathlib import Path

            cutoff_date = datetime.utcnow() - timedelta(days=days)

            # Find old completed reports
            old_reports = Report.query.filter(
                Report.status == 'completed',
                Report.generated_at < cutoff_date
            ).all()

            deleted_count = 0
            for report in old_reports:
                try:
                    # Delete file if exists
                    if report.file_path and Path(report.file_path).exists():
                        os.remove(report.file_path)

                    # Delete database record
                    db.session.delete(report)
                    deleted_count += 1
                except Exception as e:
                    app.logger.warning(f"Failed to delete report {report.id}: {str(e)}")

            db.session.commit()

            return {
                'status': 'success',
                'deleted_count': deleted_count
            }

        except Exception as e:
            app.logger.error(f"Cleanup task failed: {str(e)}")
            return {
                'status': 'failed',
                'error': str(e)
            }