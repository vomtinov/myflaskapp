import os
import logging
from flask import Flask, render_template_string
import pyodbc
import requests
from azure.storage.blob import (
    BlobServiceClient,
    generate_blob_sas,
    BlobSasPermissions
)
from datetime import datetime, timedelta

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

# ---------------- Environment Variables ----------------
account_name     = os.environ.get('STORAGE_ACCOUNT_NAME')
account_key      = os.environ.get('STORAGE_ACCOUNT_KEY')
html_container   = os.environ.get('BLOB_CONTAINER_HTML', '$web')
image_container  = os.environ.get('BLOB_CONTAINER_IMAGES')
product_container = os.environ.get('BLOB_CONTAINER_PRODUCTS', 'products')
sql_server       = os.environ.get('SQL_SERVER')
sql_db           = os.environ.get('SQL_DATABASE')
sql_user         = os.environ.get('SQL_USERNAME')
sql_pass         = os.environ.get('SQL_PASSWORD')

# ---------------- Azure Blob Service ----------------
blob_service = BlobServiceClient(
    f"https://{account_name}.blob.core.windows.net",
    credential=account_key
)

# ---------------- Generate SAS URL for Blob ----------------
def generate_sas_url(container, blob_name, expiry_hours=24):
    try:
        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=container,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(hours=expiry_hours)
        )
        return f"https://{account_name}.blob.core.windows.net/{container}/{blob_name}?{sas_token}"
    except Exception as e:
        logging.error(f"Failed to generate SAS URL: {e}")
        return ""

# ---------------- Fetch HTML Content from $web ----------------
def fetch_html_from_blob(html_filename):
    try:
        sas_url = generate_sas_url(html_container, html_filename)
        resp = requests.get(sas_url)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logging.error(f"Error fetching HTML from blob: {e}")
        return "<h1>Could not load content</h1>"

# ---------------- Fetch Product Data from Blob ----------------
def fetch_products():
    try:
        product_json_url = generate_sas_url(product_container, "product.json")
        resp = requests.get(product_json_url)
        resp.raise_for_status()
        products = resp.json()
        for product in products:
            product['image_url'] = generate_sas_url(image_container, product['image_url'].split('/')[-1])
        return products
    except Exception as e:
        logging.error(f"Failed to fetch product JSON: {e}")
        return []

# ---------------- Insert Order into SQL DB ----------------
def insert_order(product_name, price):
    try:
        conn = pyodbc.connect(
            f"Driver={{ODBC Driver 17 for SQL Server}};"
            f"Server={sql_server};"
            f"Database={sql_db};"
            f"Uid={sql_user};"
            f"Pwd={sql_pass};"
            f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
        )
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO orders (product_name, price, status) VALUES (?, ?, ?)",
            product_name, price, 'Ordered'
        )
        conn.commit()
        cur.close()
        conn.close()
        logging.info(f"Inserted order for: {product_name}")
    except Exception as e:
        logging.error(f"Database insertion failed: {e}")

# ---------------- Home Page Route ----------------
@app.route('/')
def home():
    try:
        products = fetch_products()
        html = fetch_html_from_blob('home.html')
        return render_template_string(html, products=products)
    except Exception as e:
        logging.error(f"Home route failed: {e}")
        return "<h1>Failed to load home page</h1>"

# ---------------- Buy Page Route ----------------
@app.route('/buy/<int:product_id>')
def buy(product_id):
    try:
        products = fetch_products()
        product = next((p for p in products if p["id"] == product_id), None)
        if not product:
            return "Product not found", 404
        insert_order(product["name"], int(product["price"]))
        html = fetch_html_from_blob('delivery.html')
        return render_template_string(html, product=product)
    except Exception as e:
        logging.error(f"Buy route failed: {e}")
        return "<h1>Failed to process order</h1>"

# ---------------- Health Check ----------------
@app.route('/health')
def health():
    return "OK", 200

# ---------------- Start Server ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
