from flask import Flask, render_template, redirect, url_for
import os
import pyodbc

app = Flask(__name__)

# Product data with 4 items
products = [
    {
        "id": 1,
        "category": "Pants",
        "name": "Adidas Pants",
        "price": "₹1999",
        "image": "adidas_pant.jpg"
    },
    {
        "id": 2,
        "category": "Pants",
        "name": "Puma Pants",
        "price": "₹1799",
        "image": "puma_pant.jpg"
    },
    {
        "id": 3,
        "category": "Shirts",
        "name": "Adidas T-Shirt",
        "price": "₹1299",
        "image": "adidas_tshirt.jpg"
    },
    {
        "id": 4,
        "category": "Shirts",
        "name": "Puma T-Shirt",
        "price": "₹1399",
        "image": "puma_tshirt.jpg"
    }
]

# DB insert function
def insert_order(product_name, price):
    try:
        conn = pyodbc.connect(
            f"Driver={{ODBC Driver 17 for SQL Server}};"
            f"Server={os.environ['SQL_SERVER']};"
            f"Database={os.environ['SQL_DATABASE']};"
            f"Uid={os.environ['SQL_USERNAME']};"
            f"Pwd={os.environ['SQL_PASSWORD']};"
            f"Encrypt=yes;"
            f"TrustServerCertificate=no;"
            f"Connection Timeout=30;"
        )
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO orders (product_name, price, status) VALUES (?, ?, ?)",
            product_name, price, 'Ordered'
        )
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ Order inserted successfully.")
    except Exception as e:
        print("❌ DB Error:", e)

# Home route
@app.route('/')
def home():
    return render_template("home.html", products=products)

# Buy route → store order in DB
@app.route('/buy/<int:product_id>')
def buy(product_id):
    product = next((p for p in products if p["id"] == product_id), None)
    if product:
        price = int(product["price"].replace("₹", ""))
        insert_order(product["name"], price)
        return render_template("delivery.html", product=product)
    return "Product not found", 404

# Run locally (ignored on Azure)
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000)
