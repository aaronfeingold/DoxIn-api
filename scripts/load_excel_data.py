#!/usr/bin/env python3
"""
Excel to PostgreSQL Data Ingestion Pipeline
Loads Case Study Data.xlsx into the database using the normalized schema
Enhanced with admin user tracking and bulk audit logging
"""

import pandas as pd
import numpy as np
import sys
import os
import argparse
from pathlib import Path
from datetime import datetime

# Add the backend directory to the Python path
sys.path.append(str(Path(__file__).parent.parent))

from app.models import (
    SalesTerritory, ProductCategory, ProductSubCategory,
    Product, Company, Salesperson, Invoice, InvoiceLineItem, User, AuditLog
)
from app import create_app, db
from config import Config

# ANSI color codes for console output
class Colors:
    GREEN = '\033[92m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    END = '\033[0m'

class ExcelDataLoader:
    """Load Excel data into PostgreSQL database with audit tracking"""

    def __init__(self, excel_path: str, database_url: str, admin_email: str = None):
        self.excel_path = excel_path
        self.database_url = database_url
        self.sheets = {}
        self.admin_email = admin_email
        self.admin_user = None
        # Create Flask app for database access
        self.app = create_app('development')
        self.app.config['SQLALCHEMY_DATABASE_URI'] = database_url

    def load_excel_sheets(self):
        """Load all Excel sheets into memory"""
        print("Loading Excel sheets...")
        xl_file = pd.ExcelFile(self.excel_path)

        for sheet_name in xl_file.sheet_names:
            print(f"Loading sheet: {sheet_name}")
            self.sheets[sheet_name] = pd.read_excel(self.excel_path, sheet_name=sheet_name)
            print(f"  Loaded {len(self.sheets[sheet_name])} records")

        print(f"Loaded {len(self.sheets)} sheets successfully")

    def validate_admin_user(self):
        """Validate that the admin user exists"""
        if not self.admin_email:
            print("Warning: No admin email provided. Audit logs will show 'system' as the user.")
            return True

        with self.app.app_context():
            try:
                user = User.query.filter_by(email=self.admin_email).first()
                if not user:
                    print(f"Error: Admin user {self.admin_email} not found in database.")
                    print("Create the user first or run without --admin parameter.")
                    return False

                if user.role != 'admin':
                    print(f"Error: User {self.admin_email} is not an admin.")
                    return False

                self.admin_user = user
                print(f"{Colors.GREEN}[SUCCESS]{Colors.END} Admin user validated: {self.admin_email}")
                return True

            except Exception as e:
                print(f"Error validating admin user: {e}")
                return False

    def create_bulk_audit_log(self, table_name, record_count, action="BULK_IMPORT"):
        """Create a bulk audit log entry for imported data"""
        if not self.admin_email:
            return

        with self.app.app_context():
            try:
                audit_entry = AuditLog(
                    table_name=table_name,
                    record_id=None,  # Bulk operation, no specific record
                    action=action,
                    old_values=None,
                    new_values={
                        "bulk_import": True,
                        "records_imported": record_count,
                        "source": "Excel import",
                        "excel_file": os.path.basename(self.excel_path)
                    },
                    changed_fields=[],
                    changed_by=self.admin_email,
                    change_reason=f"Bulk import of {record_count} records from Excel"
                )
                db.session.add(audit_entry)
                db.session.commit()
                print(f"  {Colors.CYAN}[AUDIT]{Colors.END} Audit log created: {record_count} records imported to {table_name}")

            except Exception as e:
                print(f"Warning: Failed to create audit log for {table_name}: {e}")
                db.session.rollback()

    def create_tables(self):
        """Create database tables if they don't exist"""
        print("Creating database tables...")
        with self.app.app_context():
            db.create_all()
        print("Database tables created successfully")

    def load_reference_data(self):
        """Load reference/lookup tables first"""
        with self.app.app_context():
            try:
                # Load Sales Territories
                print("Loading sales territories...")
                territory_df = self.sheets['SalesTerritory']
                for _, row in territory_df.iterrows():
                    # Check if territory already exists
                    territory = SalesTerritory.query.filter_by(territory_id=int(row['TerritoryID'])).first()
                    if not territory:
                        territory = SalesTerritory(
                            territory_id=int(row['TerritoryID']),
                            name=row['Name'],
                            country_region_code=row['CountryRegionCode'],
                            territory_group=row['Group'],
                            is_active=True
                        )
                        db.session.add(territory)
                    else:
                        # Update existing
                        territory.name = row['Name']
                        territory.country_region_code = row['CountryRegionCode']
                        territory.territory_group = row['Group']
                        territory.is_active = True
                db.session.commit()
                print(f"Loaded {len(territory_df)} sales territories")
                self.create_bulk_audit_log('sales_territories', len(territory_df))

                # Load Product Categories
                print("Loading product categories...")
                category_df = self.sheets['ProductCategory']
                for _, row in category_df.iterrows():
                    category = ProductCategory.query.filter_by(category_id=int(row['ProductCategoryID'])).first()
                    if not category:
                        category = ProductCategory(
                            category_id=int(row['ProductCategoryID']),
                            name=row['Name']
                        )
                        db.session.add(category)
                    else:
                        category.name = row['Name']
                db.session.commit()
                print(f"Loaded {len(category_df)} product categories")
                self.create_bulk_audit_log('product_categories', len(category_df))

                # Load Product Subcategories
                print("Loading product subcategories...")
                subcategory_df = self.sheets['ProductSubCategory']
                for _, row in subcategory_df.iterrows():
                    subcategory = ProductSubCategory.query.filter_by(subcategory_id=int(row['ProductSubcategoryID'])).first()
                    if not subcategory:
                        subcategory = ProductSubCategory(
                            subcategory_id=int(row['ProductSubcategoryID']),
                            category_id=int(row['ProductCategoryID']),
                            name=row['Name']
                        )
                        db.session.add(subcategory)
                    else:
                        subcategory.category_id = int(row['ProductCategoryID'])
                        subcategory.name = row['Name']
                db.session.commit()
                print(f"Loaded {len(subcategory_df)} product subcategories")
                self.create_bulk_audit_log('product_subcategories', len(subcategory_df))

            except Exception as e:
                db.session.rollback()
                print(f"Error loading reference data: {e}")
                raise

    def load_products(self):
        """Load products data"""
        with self.app.app_context():
            try:
                print("Loading products...")
                product_df = self.sheets['Product']

                for _, row in product_df.iterrows():
                    # Check if product already exists
                    product = Product.query.filter_by(product_id=int(row['ProductID'])).first()
                    if not product:
                        product = Product(
                            product_id=int(row['ProductID']),
                            item_number=row['ProductNumber'],
                            name=row['Name'],
                            color=row['Color'] if pd.notna(row['Color']) else None,
                            size=row['Size'] if pd.notna(row['Size']) else None,
                            product_line=row['ProductLine'] if pd.notna(row['ProductLine']) else None,
                            class_attr=row['Class'] if pd.notna(row['Class']) else None,
                            style=row['Style'] if pd.notna(row['Style']) else None,
                            standard_cost=float(row['StandardCost']) if pd.notna(row['StandardCost']) else None,
                            list_price=float(row['ListPrice']) if pd.notna(row['ListPrice']) else None,
                            make_flag=bool(row['MakeFlag']),
                            finished_goods_flag=bool(row['FinishedGoodsFlag']),
                            subcategory_id=int(row['ProductSubcategoryID']) if pd.notna(row['ProductSubcategoryID']) else None,
                            product_model_id=int(row['ProductModelID']) if pd.notna(row['ProductModelID']) else None,
                            is_active=True
                        )
                        db.session.add(product)
                    else:
                        # Update existing
                        product.item_number = row['ProductNumber']
                        product.name = row['Name']
                        product.color = row['Color'] if pd.notna(row['Color']) else None
                        product.size = row['Size'] if pd.notna(row['Size']) else None
                        product.product_line = row['ProductLine'] if pd.notna(row['ProductLine']) else None
                        product.class_attr = row['Class'] if pd.notna(row['Class']) else None
                        product.style = row['Style'] if pd.notna(row['Style']) else None
                        product.standard_cost = float(row['StandardCost']) if pd.notna(row['StandardCost']) else None
                        product.list_price = float(row['ListPrice']) if pd.notna(row['ListPrice']) else None
                        product.make_flag = bool(row['MakeFlag'])
                        product.finished_goods_flag = bool(row['FinishedGoodsFlag'])
                        product.subcategory_id = int(row['ProductSubcategoryID']) if pd.notna(row['ProductSubcategoryID']) else None
                        product.product_model_id = int(row['ProductModelID']) if pd.notna(row['ProductModelID']) else None
                        product.is_active = True

                db.session.commit()
                print(f"Loaded {len(product_df)} products")
                self.create_bulk_audit_log('products', len(product_df))

            except Exception as e:
                db.session.rollback()
                print(f"Error loading products: {e}")
                raise

    def load_customers(self):
        """Load and merge customer data from multiple sheets"""
        with self.app.app_context():
            try:
                print("Loading customers...")

                customers_df = self.sheets['Customers']
                individuals_df = self.sheets['IndividualCustomers']
                stores_df = self.sheets['StoreCustomers']

                # Create lookup dictionaries (handle potential duplicates by taking first occurrence)
                person_lookup = {}
                for _, row in individuals_df.iterrows():
                    business_id = int(row['BusinessEntityID'])
                    if business_id not in person_lookup:
                        person_lookup[business_id] = row.to_dict()

                store_lookup = {}
                for _, row in stores_df.iterrows():
                    business_id = int(row['BusinessEntityID'])
                    if business_id not in store_lookup:
                        store_lookup[business_id] = row.to_dict()

                for _, row in customers_df.iterrows():
                    customer_id = int(row['CustomerID'])
                    person_id = int(row['PersonID']) if pd.notna(row['PersonID']) else None
                    store_id = int(row['StoreID']) if pd.notna(row['StoreID']) else None

                    # Determine customer type and get details
                    if person_id and person_id in person_lookup:
                        # Individual customer
                        person_data = person_lookup[person_id]
                        company = Company(
                            customer_id=customer_id,
                            business_entity_id=person_id,
                            account_number=row['AccountNumber'],
                            company_type='individual',
                            first_name=person_data['FirstName'],
                            middle_name=person_data['MiddleName'] if pd.notna(person_data['MiddleName']) else None,
                            last_name=person_data['LastName'],
                            address_type=person_data['AddressType'],
                            street_address=person_data['AddressLine1'],
                            address_line2=person_data['AddressLine2'] if pd.notna(person_data['AddressLine2']) else None,
                            city=person_data['City'],
                            state_province=person_data['StateProvinceName'],
                            postal_code=person_data['PostalCode'],
                            country_region=person_data['CountryRegionName'],
                            territory_id=int(row['TerritoryID']),
                            is_active=True
                        )
                    elif store_id and store_id in store_lookup:
                        # Business customer
                        store_data = store_lookup[store_id]
                        company = Company(
                            customer_id=customer_id,
                            business_entity_id=store_id,
                            account_number=row['AccountNumber'],
                            company_type='business',
                            company_name=store_data['Name'],
                            address_type=store_data['AddressType'],
                            street_address=store_data['AddressLine1'],
                            address_line2=store_data['AddressLine2'] if pd.notna(store_data['AddressLine2']) else None,
                            city=store_data['City'],
                            state_province=store_data['StateProvinceName'],
                            postal_code=store_data['PostalCode'],
                            country_region=store_data['CountryRegionName'],
                            territory_id=int(row['TerritoryID']),
                            is_active=True
                        )
                    else:
                        # Fallback - create basic customer record
                        company = Company(
                            customer_id=customer_id,
                            account_number=row['AccountNumber'],
                            company_type='unknown',
                            territory_id=int(row['TerritoryID']),
                            is_active=True
                        )

                    # Check if company already exists
                    existing_company = Company.query.filter_by(customer_id=customer_id).first()
                    if not existing_company:
                        db.session.add(company)
                    else:
                        # Update existing
                        for key, value in company.__dict__.items():
                            if not key.startswith('_') and key not in ['id', 'created_at', 'updated_at']:
                                setattr(existing_company, key, value)

                db.session.commit()
                print(f"Loaded {len(customers_df)} customers")
                self.create_bulk_audit_log('companies', len(customers_df))

            except Exception as e:
                db.session.rollback()
                print(f"Error loading customers: {e}")
                raise

    def load_invoices(self):
        """Load invoice headers and line items"""
        with self.app.app_context():
            try:
                print("Loading invoices...")

                header_df = self.sheets['SalesOrderHeader']
                detail_df = self.sheets['SalesOrderDetail']

                # Load invoice headers first
                for _, row in header_df.iterrows():
                    # Find the corresponding customer
                    customer = Company.query.filter_by(customer_id=int(row['CustomerID'])).first()
                    if not customer:
                        print(f"Warning: Customer {row['CustomerID']} not found for invoice {row['SalesOrderID']}")
                        continue

                    # Find salesperson if exists
                    salesperson = None
                    if pd.notna(row['SalesPersonID']):
                        # For now, we'll create a basic salesperson record if it doesn't exist
                        salesperson_id = int(row['SalesPersonID'])
                        salesperson = Salesperson.query.filter_by(salesperson_id=salesperson_id).first()
                        if not salesperson:
                            salesperson = Salesperson(
                                salesperson_id=salesperson_id,
                                name=f"Salesperson {salesperson_id}",
                                is_active=True
                            )
                            db.session.add(salesperson)
                            db.session.flush()  # Flush to get the UUID without committing

                    invoice = Invoice(
                        sales_order_id=int(row['SalesOrderID']),
                        invoice_number=row['SalesOrderNumber'],
                        revision_number=int(row['RevisionNumber']),
                        invoice_date=row['OrderDate'].date(),
                        due_date=row['DueDate'].date(),
                        ship_date=row['ShipDate'].date() if pd.notna(row['ShipDate']) else None,
                        customer_id=customer.id,
                        salesperson_id=salesperson.id if salesperson else None,
                        territory_id=int(row['TerritoryID']),
                        bill_to_address_id=int(row['BillToAddressID']),
                        ship_to_address_id=int(row['ShipToAddressID']),
                        ship_method_id=int(row['ShipMethodID']),
                        account_number=row['AccountNumber'],
                        po_number=row['PurchaseOrderNumber'] if pd.notna(row['PurchaseOrderNumber']) else None,
                        credit_card_id=int(row['CreditCardID']) if pd.notna(row['CreditCardID']) else None,
                        credit_card_approval_code=row['CreditCardApprovalCode'] if pd.notna(row['CreditCardApprovalCode']) else None,
                        currency_rate_id=int(row['CurrencyRateID']) if pd.notna(row['CurrencyRateID']) else None,
                        subtotal=float(row['SubTotal']),
                        tax_amount=float(row['TaxAmt']),
                        freight=float(row['Freight']),
                        total_amount=float(row['TotalDue']),
                        order_status=int(row['Status']),
                        online_order_flag=bool(row['OnlineOrderFlag']),
                        processed_by_llm=False,
                        requires_review=False
                    )
                    # Check if invoice already exists
                    existing_invoice = Invoice.query.filter_by(sales_order_id=int(row['SalesOrderID'])).first()
                    if not existing_invoice:
                        db.session.add(invoice)
                    else:
                        # Update existing
                        for key, value in invoice.__dict__.items():
                            if not key.startswith('_') and key not in ['id', 'created_at', 'updated_at']:
                                setattr(existing_invoice, key, value)

                db.session.commit()
                print(f"Loaded {len(header_df)} invoice headers")
                self.create_bulk_audit_log('invoices', len(header_df))

                # Load line items
                print("Loading invoice line items...")
                line_items_loaded = 0

                for _, row in detail_df.iterrows():
                    # Find the invoice
                    invoice = Invoice.query.filter_by(sales_order_id=int(row['SalesOrderID'])).first()
                    if not invoice:
                        print(f"Warning: Invoice {row['SalesOrderID']} not found for line item {row['SalesOrderDetailID']}")
                        continue

                    # Find the product
                    product = Product.query.filter_by(product_id=int(row['ProductID'])).first()

                    line_item = InvoiceLineItem(
                        invoice_id=invoice.id,
                        sales_order_detail_id=int(row['SalesOrderDetailID']),
                        line_number=line_items_loaded + 1,  # Simple sequential numbering
                        product_id=product.id if product else None,
                        item_number=product.item_number if product else str(row['ProductID']),
                        description=product.name if product else f"Product {row['ProductID']}",
                        quantity=int(row['OrderQty']),
                        unit_price=float(row['UnitPrice']),
                        unit_price_discount=float(row['UnitPriceDiscount']),
                        line_total=float(row['LineTotal']),
                        special_offer_id=int(row['SpecialOfferID']),
                        carrier_tracking_number=row['CarrierTrackingNumber'] if pd.notna(row['CarrierTrackingNumber']) else None
                    )
                    # Check if line item already exists
                    existing_line = InvoiceLineItem.query.filter_by(sales_order_detail_id=int(row['SalesOrderDetailID'])).first()
                    if not existing_line:
                        db.session.add(line_item)
                    else:
                        # Update existing
                        for key, value in line_item.__dict__.items():
                            if not key.startswith('_') and key not in ['id', 'created_at', 'updated_at']:
                                setattr(existing_line, key, value)
                    line_items_loaded += 1

                    # Commit in batches for performance
                    if line_items_loaded % 1000 == 0:
                        db.session.commit()
                        print(f"  Loaded {line_items_loaded} line items...")

                db.session.commit()
                print(f"Loaded {line_items_loaded} invoice line items")
                self.create_bulk_audit_log('invoice_line_items', line_items_loaded)

            except Exception as e:
                db.session.rollback()
                print(f"Error loading invoices: {e}")
                raise

    def run_full_import(self):
        """Run the complete data import process"""
        print("=" * 60)
        print(f"{Colors.BLUE}EXCEL TO POSTGRESQL DATA IMPORT{Colors.END}")
        print("=" * 60)
        print(f"Excel file: {self.excel_path}")
        print(f"Database: {self.database_url}")
        print()

        try:
            # Load Excel data
            self.load_excel_sheets()
            print()

            # Create tables
            self.create_tables()
            print()

            # Import data in dependency order
            self.load_reference_data()
            print()

            self.load_products()
            print()

            self.load_customers()
            print()

            self.load_invoices()
            print()

            print("=" * 60)
            print(f"{Colors.GREEN}[SUCCESS]{Colors.END} DATA IMPORT COMPLETED SUCCESSFULLY")
            print("=" * 60)

            # Print summary statistics
            self.print_import_summary()

        except Exception as e:
            print("=" * 60)
            print(f"{Colors.RED}[ERROR]{Colors.END} DATA IMPORT FAILED")
            print("=" * 60)
            print(f"Error: {e}")
            raise

    def print_import_summary(self):
        """Print summary of imported data"""
        with self.app.app_context():
            try:
                print("\nIMPORT SUMMARY:")
                print("-" * 40)

                territory_count = SalesTerritory.query.count()
                category_count = ProductCategory.query.count()
                subcategory_count = ProductSubCategory.query.count()
                product_count = Product.query.count()
                company_count = Company.query.count()
                salesperson_count = Salesperson.query.count()
                invoice_count = Invoice.query.count()
                line_item_count = InvoiceLineItem.query.count()

                print(f"Sales Territories: {territory_count}")
                print(f"Product Categories: {category_count}")
                print(f"Product Subcategories: {subcategory_count}")
                print(f"Products: {product_count}")
                print(f"Companies: {company_count}")
                print(f"Salespersons: {salesperson_count}")
                print(f"Invoices: {invoice_count}")
                print(f"Line Items: {line_item_count}")
                print()

                # Calculate some business metrics
                from sqlalchemy import func
                total_revenue = db.session.query(func.sum(Invoice.total_amount)).scalar()
                if total_revenue and invoice_count > 0:
                    print(f"Total Revenue Loaded: ${total_revenue:,.2f}")
                    print(f"Average Order Value: ${total_revenue/invoice_count:,.2f}")

            except Exception as e:
                print(f"Error generating summary: {e}")


def main():
    """Main function with command line argument parsing"""
    parser = argparse.ArgumentParser(
        description="Import Excel data into PostgreSQL database with audit tracking"
    )
    parser.add_argument(
        "excel_path",
        nargs="?",
        default="/home/aaronfeingold/Code/stryker/assets/Case Study Data.xlsx",
        help="Path to Excel file (default: assets/Case Study Data.xlsx)"
    )
    parser.add_argument(
        "--database-url",
        default=Config.SQLALCHEMY_DATABASE_URI,
        help="Database URL (default: from config)"
    )
    parser.add_argument(
        "--admin",
        help="Admin user email for audit logging (e.g. admin@case-study.local)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be imported without making changes"
    )

    args = parser.parse_args()

    # Validate file exists
    if not os.path.exists(args.excel_path):
        print(f"{Colors.RED}[ERROR]{Colors.END} Excel file not found at {args.excel_path}")
        sys.exit(1)

    # Create loader
    loader = ExcelDataLoader(args.excel_path, args.database_url, args.admin)

    # Validate admin user if provided
    if args.admin and not loader.validate_admin_user():
        sys.exit(1)

    # Dry run mode
    if args.dry_run:
        print("DRY RUN MODE - No changes will be made")
        loader.load_excel_sheets()
        loader.show_import_summary()
        return

    # Run the import
    print(f"Starting Excel import from: {args.excel_path}")
    if args.admin:
        print(f"Audit logs will be created for admin user: {args.admin}")
    else:
        print("No admin user specified - audit logs will show 'system'")

    loader.run_full_import()


if __name__ == "__main__":
    main()
