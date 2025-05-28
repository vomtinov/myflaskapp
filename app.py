import os
import logging
from flask import Flask, render_template_string, redirect, url_for
import pyodbc
import requests
from azure.storage.blob import (
    BlobServiceClient,
    generate_blob_sas,
    BlobSasPermissions
)
from datetime import datetime, timedelta

app = Flask(__name__)

# Initialize BlobServiceClient
account_name = os.environ['STORAGE_ACCOUNT_NAME']
account_key  = os.environ['STORAGE_ACCOUNT_KEY']
blob_service = BlobServiceClient(
    f"https://{account_name}.blob.core.windows.net",
    credential=account_key
)

# Containers
HTML_CONTAINER   = os.environ.get('BLOB_CONTAINER_HTML', '$web')
IMAGE_CONTAINER  = os.environ['BLOB_CONTAINER_IMAGES']

# Product catalog (only blob filenames)
products = [
    {"id":1, "category":"Pants",  "name":"Adidas Pants",    "price":"₹1999", "blob":"adidas_pant.jpg"},
    {"id":2, "category":"Pants",  "name":"Puma Pants",     "price":"₹1799", "blob":"puma_pant.jpg"},
    {"id":3, "category":"Shirts", "name":"Adidas T-Shirt", "price":"₹1299", "blob":"adidas_tshirt.jpg"},
    {"id":4, "category":"Shirts", "name":"Puma T-Shirt",    "price":"₹1399", "blob":"puma_tshirt.jpg"}
]

def generate_sas_url(container: str, blob_name: str, expiry_hours=1) -> str:
    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=container,
        blob_name=blob_name,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(hours=expiry_hours)
    )
    return f"https://{account_name}.blob.core.windows.net/{container}/{blob_name}?{sas_token}"

def fetch_html_from_blob(html_filename: str) -> str:
    """Fetches raw HTML from the $web (static website) container."""
    url = f"https://{account_name}.z22.web.core.windows.net/{html_filename}"
    # If you didn't enable static website, use a SAS URL instead:
    # url = generate_sas_url(HTML_CONTAINER, html_filename)
    resp = requests.get(url)
    resp.raise_for_status()
    return resp.text

# DB insert as before
def insert_order(product_name, price):
    try:
        conn = pyodbc.connect(
            f"Driver={{ODBC Driver 17 for SQL Server}};"
            f"Server={os.environ['SQL_SERVER']};"
            f"Database={os.environ['SQL_DATABASE']};"
            f"Uid={os.environ['SQL_USERNAME']};"
            f"Pwd={os.environ['SQL_PASSWORD']};"
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
    except Exception as e:
        logging.error("DB Error: %s", e)

@app.route('/')
def home():
    # Generate SAS URLs for images
    for p in products:
        p['image_url'] = generate_sas_url(IMAGE_CONTAINER, p['blob'], expiry_hours=24)
    # Fetch the static HTML template from blob
    html = fetch_html_from_blob('home.html')
    return render_template_string(html, products=products)

@app.route('/buy/<int:product_id>')
def buy(product_id):
    product = next((p for p in products if p["id"]==product_id), None)
    if not product:
        return "Product not found", 404

    price_int = int(product['price'].replace("₹",""))
    insert_order(product['name'], price_int)

    # Regenerate image URL
    product['image_url'] = generate_sas_url(IMAGE_CONTAINER, product['blob'], expiry_hours=24)
    # Fetch delivery HTML
    html = fetch_html_from_blob('delivery.html')
    return render_template_string(html, product=product)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000)
