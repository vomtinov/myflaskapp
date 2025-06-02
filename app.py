import os
import logging
import json
from datetime import datetime, timedelta

import pyodbc
import requests
from flask import Flask, render_template_string, request
from azure.storage.blob import (
    BlobServiceClient,
    generate_blob_sas,
    BlobSasPermissions
)
from azure.storage.queue import QueueClient

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

# ---------------- Ensure Required Environment Variables ----------------
required_env = [
    'STORAGE_ACCOUNT_NAME',
    'STORAGE_ACCOUNT_KEY',
    'BLOB_CONTAINER_IMAGES',
    'SQL_SERVER',
    'SQL_DATABASE',
    'SQL_USERNAME',
    'SQL_PASSWORD',
    'AzureWebJobsStorage',       # for queue connection
]
missing = [key for key in required_env if key not in os.environ]
if missing:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

# These two are optional (defaults: $web and products)
html_container    = os.environ.get('BLOB_CONTAINER_HTML', '$web')
product_container = os.environ.get('BLOB_CONTAINER_PRODUCTS', 'products')

# Required ones
account_name    = os.environ['STORAGE_ACCOUNT_NAME']
account_key     = os.environ['STORAGE_ACCOUNT_KEY']
image_container = os.environ['BLOB_CONTAINER_IMAGES']
sql_server      = os.environ['SQL_SERVER']
sql_db          = os.environ['SQL_DATABASE']
sql_user        = os.environ['SQL_USERNAME']
sql_pass        = os.environ['SQL_PASSWORD']

# The queue name defaults to "orders-queue" if ORDER_QUEUE isn’t set
queue_name      = os.environ.get('ORDER_QUEUE', 'orders-queue')
queue_conn_str  = os.environ['AzureWebJobsStorage']

# ---------------- Azure Blob Client ----------------
blob_service = BlobServiceClient(
    f"https://{account_name}.blob.core.windows.net",
    credential=account_key
)

# ---------------- Helper: Generate a SAS URL ----------------
def generate_sas_url(container: str, blob_name: str, expiry_hours: int = 24) -> str:
    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=container,
        blob_name=blob_name,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(hours=expiry_hours)
    )
    return f"https://{account_name}.blob.core.windows.net/{container}/{blob_name}?{sas_token}"

# ---------------- Helper: Fetch HTML Template from Blob ----------------
def fetch_html_from_blob(blob_name: str) -> str:
    sas_url = generate_sas_url(html_container, blob_name)
    logging.info(f"Fetching HTML from blob: {sas_url}")
    resp = requests.get(sas_url)
    resp.raise_for_status()
    return resp.text

# ---------------- Helper: Fetch Products JSON from Blob ----------------
def fetch_products() -> list:
    sas_url = generate_sas_url(product_container, "product.json")
    logging.info(f"Fetching products JSON from blob: {sas_url}")
    resp = requests.get(sas_url)
    resp.raise_for_status()
    items = resp.json()
    # Replace each product's image_url with a full SAS URL to the 'images' container
    for p in items:
        filename = p.get('image_url', '').split('/')[-1]
        p['image_url'] = generate_sas_url(image_container, filename)
    return items

# ---------------- Helper: Enqueue Order into Azure Queue ----------------
def enqueue_order(product: dict):
    # Build the JSON message
    msg_payload = {
        "id":    product['id'],
        "name":  product['name'],
        "price": int(product['price'])
    }
    msg_text = json.dumps(msg_payload)

    # Create the QueueClient from connection string + queue name
    queue_client = QueueClient.from_connection_string(queue_conn_str, queue_name)
    logging.info(f"Sending message to queue '{queue_name}': {msg_text}")
    queue_client.send_message(msg_text)
    logging.info(f"Enqueued order: {msg_text}")

# ---------------- (Not used directly in web app) Insert Order to SQL -----------
# Kept here for your Function to use
def insert_order(product_name: str, price: int):
    conn_str = (
        f"Driver={{ODBC Driver 17 for SQL Server}};"
        f"Server={sql_server};Database={sql_db};"
        f"Uid={sql_user};Pwd={sql_pass};"
        "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )
    conn = pyodbc.connect(conn_str)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO orders (product_name, price, status) VALUES (?, ?, ?)",
        product_name, price, 'Ordered'
    )
    conn.commit()
    conn.close()
    logging.info(f"Inserted order into SQL: {product_name}")

# ---------------- Home Route ----------------
@app.route('/')
def home():
    try:
        q = request.args.get("q", "").lower().strip()
        products = fetch_products()
        if q:
            products = [
                p for p in products
                if q in p.get('name', '').lower() or q in p.get('category', '').lower()
            ]
        html = fetch_html_from_blob("home.html")
        return render_template_string(html, products=products)
    except Exception as e:
        logging.exception("Error in / (home) route")
        return f"🛑 500 in home(): {e}", 500

# ---------------- Buy Route ----------------
@app.route('/buy/<int:product_id>')
def buy(product_id):
    try:
        products = fetch_products()
        product  = next((p for p in products if p['id'] == product_id), None)
        if not product:
            return "Product not found", 404

        enqueue_order(product)
        html = fetch_html_from_blob("delivery.html")
        return render_template_string(html, product=product)

    except Exception as e:
        logging.exception("Error in /buy route")
        # Return the raw exception text for debugging; remove in production
        return f"🛑 500 in /buy: {e}", 500

# ---------------- Health Check ----------------
@app.route('/health')
def health():
    return "OK", 200

# ---------------- Run Locally (Ignored on App Service) ----------------
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000)
