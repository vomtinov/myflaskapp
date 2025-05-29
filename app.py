import os
import logging
from flask import Flask, render_template_string, request
import pyodbc
import requests
from azure.storage.blob import (
    BlobServiceClient,
    generate_blob_sas,
    BlobSasPermissions
)
from azure.storage.queue import QueueClient
from datetime import datetime, timedelta
import json

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

# ---------------- Environment Variables ----------------
account_name      = os.environ['STORAGE_ACCOUNT_NAME']
account_key       = os.environ['STORAGE_ACCOUNT_KEY']
html_container    = os.environ.get('BLOB_CONTAINER_HTML', '$web')
image_container   = os.environ['BLOB_CONTAINER_IMAGES']
product_container = os.environ.get('BLOB_CONTAINER_PRODUCTS', 'products')
queue_name        = os.environ.get('ORDER_QUEUE', 'orders-queue')  # new
sql_server        = os.environ['SQL_SERVER']
sql_db            = os.environ['SQL_DATABASE']
sql_user          = os.environ['SQL_USERNAME']
sql_pass          = os.environ['SQL_PASSWORD']

# ---------------- Azure Blob & Queue Clients ----------------
blob_service = BlobServiceClient(
    f"https://{account_name}.blob.core.windows.net",
    credential=account_key
)

queue_client = QueueClient(
    f"https://{account_name}.queue.core.windows.net",
    queue_name,
    credential=account_key
)

# ---------------- Generate SAS URL for Blob ----------------
def generate_sas_url(container, blob_name, expiry_hours=24):
    sas = generate_blob_sas(
        account_name=account_name,
        container_name=container,
        blob_name=blob_name,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(hours=expiry_hours)
    )
    return f"https://{account_name}.blob.core.windows.net/{container}/{blob_name}?{sas}"

# ---------------- Fetch HTML from Blob ----------------
def fetch_html_from_blob(name):
    url = generate_sas_url(html_container, name)
    r = requests.get(url); r.raise_for_status()
    return r.text

# ---------------- Fetch Products ----------------
def fetch_products():
    url = generate_sas_url(product_container, "product.json")
    r = requests.get(url); r.raise_for_status()
    items = r.json()
    for p in items:
        fn = p['image_url'].split("/")[-1]
        p['image_url'] = generate_sas_url(image_container, fn)
    return items

# ---------------- Enqueue Order ----------------
def enqueue_order(product):
    msg = json.dumps({
        "id":    product['id'],
        "name":  product['name'],
        "price": int(product['price'])
    })
    queue_client.send_message(msg)
    logging.info(f"Enqueued order: {msg}")

# ---------------- Insert Order (for Function) ----------------
def insert_order(product_name, price):
    conn = pyodbc.connect(
        f"Driver={{ODBC Driver 17 for SQL Server}};"
        f"Server={sql_server};Database={sql_db};"
        f"Uid={sql_user};Pwd={sql_pass};"
        "Encrypt=yes;TrustServerCertificate=no;"
    )
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
    q = request.args.get("q", "").lower().strip()
    products = fetch_products()
    if q:
        products = [p for p in products if q in p['name'].lower() or q in p['category'].lower()]
    html = fetch_html_from_blob("home.html")
    return render_template_string(html, products=products)

# ---------------- Buy Route ----------------
@app.route('/buy/<int:product_id>')
def buy(product_id):
    products = fetch_products()
    product  = next((p for p in products if p['id']==product_id), None)
    if not product:
        return "Product not found", 404

    # enqueue instead of direct DB insert
    enqueue_order(product)

    html = fetch_html_from_blob("delivery.html")
    return render_template_string(html, product=product)

# ---------------- Health Check ----------------
@app.route('/health')
def health():
    return "OK", 200

# ---------------- Run ----------------
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000)
