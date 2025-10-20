# Data Ingestion Pipeline

This document explains how to load the Case Study Data.xlsx file into the PostgreSQL database.

## Overview

The data ingestion pipeline transforms Excel data from a denormalized sales order format into our optimized invoice processing schema. This demonstrates the value of proper database normalization vs. a simple 1:1 Excel mapping.

## Quick Start

1. **Set up database connection:**
```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/invoices"
```

2. **Run the import:**
```bash
./load_data.sh
```

## Manual Usage

```bash
cd backend
pip install -r requirements-ingestion.txt
python scripts/load_excel_data.py [excel_file] [database_url]
```

## Data Transformation Overview

### Why Not 1:1 Excel Mapping?

The Excel file has 9 sheets in denormalized format optimized for human reading:
- `SalesOrderHeader` (31,465 records)
- `SalesOrderDetail` (121,317 records)
- `Product` (504 records)
- `Customers` (19,820 records)
- `IndividualCustomers` (18,508 records)
- `StoreCustomers` (712 records)
- `SalesTerritory` (10 records)
- `ProductCategory` (4 records)
- `ProductSubCategory` (37 records)

Our database schema reorganizes this into normalized tables optimized for:
- **Performance**: Proper indexing and relationships
- **Semantic search**: Vector embeddings for LLM-powered matching
- **Business logic**: Calculated fields and validation
- **Extensibility**: Document processing metadata, audit trails

### Key Transformations

1. **Customer Consolidation**
   - `IndividualCustomers` + `StoreCustomers` → `companies` table
   - Unified customer entity with proper address handling
   - Support for both B2C and B2B scenarios

2. **Invoice Processing Focus**
   - `SalesOrderHeader` → `invoices` (semantic naming)
   - Added document processing fields for LLM extraction
   - Enhanced validation and calculated properties

3. **Product Hierarchy**
   - Proper normalization: Categories → Subcategories → Products
   - Vector embeddings for semantic product matching
   - Missing attribute handling with defaults

4. **Data Quality Improvements**
   - Handle 50-58% missing product attributes
   - 88% missing salesperson assignments (create placeholder records)
   - Address data standardization across countries

## Import Process

The pipeline loads data in dependency order:

### Phase 1: Reference Data
```
1. SalesTerritory → sales_territories
2. ProductCategory → product_categories
3. ProductSubCategory → product_subcategories
```

### Phase 2: Master Data
```
4. Product → products (with attribute handling)
5. Customers + IndividualCustomers + StoreCustomers → companies
```

### Phase 3: Transactional Data
```
6. SalesOrderHeader → invoices
7. SalesOrderDetail → invoice_line_items
8. Auto-create missing salesperson records
```

## Expected Results

After successful import:

- **Sales Territories**: 10 records
- **Product Categories**: 4 records
- **Product Subcategories**: 37 records
- **Products**: 504 records
- **Companies**: 19,820 records
- **Salespersons**: ~17 records (auto-created)
- **Invoices**: 31,465 records
- **Line Items**: 121,317 records

**Total Revenue**: ~$123.2 million
**Average Order Value**: $3,916

## Benefits of This Approach

### vs. 1:1 Excel Import:

1. **Better Performance**
   - Normalized relationships reduce data duplication
   - Proper indexing for common queries
   - Vector similarity searches for semantic matching

2. **Enhanced Functionality**
   - Document processing workflow support
   - Real-time validation of financial calculations
   - Audit trail and change tracking

3. **Semantic Search Capabilities**
   - Company name/address fuzzy matching
   - Product description similarity search
   - Full invoice content search with embeddings

4. **Business Intelligence**
   - Customer segmentation (B2C vs B2B)
   - Product performance analysis
   - Territory-based reporting
   - Financial validation and reconciliation

5. **LLM Integration Ready**
   - Vector embeddings for all searchable text
   - Document processing metadata tracking
   - Confidence scoring and review workflows

## Troubleshooting

### Common Issues

1. **Missing Database URL**
```bash
export DATABASE_URL="postgresql://user:pass@localhost:5432/invoices"
```

2. **Excel File Not Found**
   - Ensure `assets/Case Study Data.xlsx` exists
   - Check file path in script

3. **Permission Errors**
```bash
chmod +x load_data.sh
chmod +x backend/scripts/load_excel_data.py
```

4. **Python Dependencies**
```bash
cd backend
pip install -r requirements-ingestion.txt
```

### Data Validation

The script automatically validates:
- Financial calculations (subtotals, totals)
- Foreign key relationships
- Data type conversions
- Missing value handling

Any validation errors will be reported during import.

## Next Steps

After successful data import:

1. **Start the Flask backend**
2. **Test API endpoints** with real data
3. **Generate vector embeddings** for semantic search
4. **Create test invoice templates** using real product/customer data
5. **Validate LLM extraction** against known good invoices

This demonstrates how thoughtful schema design provides significant advantages over direct Excel-to-database mapping, especially for AI/ML-powered applications.