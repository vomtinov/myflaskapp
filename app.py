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

# Logging setup
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# Load environment variables
account_name     = os.environ.get('STORAGE_ACCOUNT_NAME')
account_key      = os.environ.get('STORAGE_ACCOUNT_KEY')
html_container   = os.environ.get('BLOB_CONTAINER_HTML', '$web')  # Public static website
image_container  = os.environ.get('BLOB_CONTAINER_IMAGES')
sql_server       = os.environ.get('SQL_SERVER')
sql_db           = os.environ.get('SQL_DATABASE')
sql_user         = os.environ.get('SQL_USERNAME')
sql_pass         = os.environ.get('SQL_PASSWORD')

# Blob service client
blob_service = BlobServiceClient(
    f"https://{account_name}.blob.core.windows.net",
    credential=account_key
)

# Product list
products = [
    {"id": 1, "category": "Pants",  "name": "Adidas Pants",    "price": "₹1999", "blob": "adidas_pant.jpg"},
    {"id": 2, "category": "Pants",  "name": "Puma Pants",      "price": "₹1799", "blob": "puma_pant.jpg"},
    {"id": 3, "category": "Shirts", "name": "Adidas T-Shirt",  "price": "₹1299", "blob": "adidas_tshirt.jpg"},
    {"id": 4, "category": "Shirts", "name": "Puma T-Shirt",    "price": "₹1399", "blob": "puma_tshirt.jpg"}
]

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
        logging.error(f"SAS URL generation failed: {e}")
        return ""

def fetch_html_from_blob(filename):
    try:
        url = f"https://{account_name}.z22.web.core.windows.net/{filename}"
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logging.error(f"Error fetching HTML: {e}")
        return "<h1>Content failed to load</h1>"

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
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO orders (product_name, price, status) VALUES (?, ?, ?)",
            product_name, price, 'Ordered'
        )
        conn.commit()
        cursor.close()
        conn.close()
        logging.info(f"Order inserted: {product_name}")
    except Exception as e:
        logging.error(f"Database insertion failed: {e}")

@app.route('/')
def home():
    try:
        for product in products:
            product['image_url'] = generate_sas_url(image_container, product['blob'])
        html = fetch_html_from_blob('home.html')
        return render_template_string(html, products=products)
    except Exception as e:
        logging.error(f"Home route failed: {e}")
        return "<h1>Failed to load home</h1>"

@app.route('/buy/<int:product_id>')
def buy(product_id):
    try:
        product = next((p for p in products if p["id"] == product_id), None)
        if not product:
            return "Product not found", 404
        insert_order(product["name"], int(product["price"].replace("₹", "")))
        product['image_url'] = generate_sas_url(image_container, product['blob'])
        html = fetch_html_from_blob('delivery.html')
        return render_template_string(html, product=product)
    except Exception as e:
        logging.error(f"Buy route failed: {e}")
        return "<h1>Failed to process order</h1>"

@app.route('/health')
def health():
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
