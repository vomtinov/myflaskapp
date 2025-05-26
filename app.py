from flask import Flask, render_template, redirect, url_for

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

@app.route('/')
def home():
    return render_template("home.html", products=products)

@app.route('/buy/<int:product_id>')
def buy(product_id):
    product = next((p for p in products if p["id"] == product_id), None)
    if product:
        return render_template("delivery.html", product=product)
    return "Product not found", 404

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000)
