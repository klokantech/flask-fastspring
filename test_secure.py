from flask import Flask
from flask_fastspring import FastSpring

key = b'0123456789ABCDEF'
payload = b'Hello, world!'

app = Flask(__name__)
app.config['FASTSPRING_STOREFRONT'] = ''
app.config['FASTSPRING_USERNAME'] = ''
app.config['FASTSPRING_PASSWORD'] = ''
app.config['FASTSPRING_PRIVATE_KEY'] = 'test_secure.key'

fastspring = FastSpring(app)
print(fastspring.secure_payload(key, payload))
print(fastspring.secure_key(key))
