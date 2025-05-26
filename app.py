from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "<h1>Hello, Azure!</h1><p>Your Flask app is running! 🚀</p>"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
