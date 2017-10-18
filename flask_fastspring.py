import json
import requests

from base64 import b64encode
from cryptography.hazmat.primitives.ciphers import Cipher
from cryptography.hazmat.primitives.ciphers.algorithms import AES
from cryptography.hazmat.primitives.ciphers.modes import ECB
from cryptography.hazmat.primitives.padding import PKCS7
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from datetime import datetime
from flask import Markup, current_app, render_template_string
from os import urandom
from psycopg2.tz import FixedOffsetTimezone
from sqlalchemy import Boolean, Column, DateTime, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import deferred


class FastSpring:

    def __init__(self, app=None):
        self.debug = None
        self.storefront = None
        self.username = None
        self.password = None
        self.openssl = None
        self.access_key = None
        self.private_key = None
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize the extension.

        To authenticate with FastSpring API, configure the
        FASTSPRING_USERNAME and FASTSPRING_PASSWORD options.
        The FASTSPRING_STOREFRONT option determines which
        storefront will be used, ie. testing or production.
        Because FastSpring actually has a testing mode, these
        options are all mandatory.

        For secure payloads, configure the path to the RSA
        private key with the FASTSPRING_PRIVATE_KEY option,
        and the API access key with the FASTSPRING_ACCESS_KEY
        option.
        """
        app.extensions['fastspring'] = self
        self.debug = app.debug
        self.storefront = app.config['FASTSPRING_STOREFRONT']
        self.username = app.config['FASTSPRING_USERNAME']
        self.password = app.config['FASTSPRING_PASSWORD']
        self.access_key = app.config.get('FASTSPRING_ACCESS_KEY')
        if self.debug:
            return
        private_key = app.config.get('FASTSPRING_PRIVATE_KEY')
        if private_key is not None:
            from cryptography.hazmat.backends.openssl.backend import backend
            self.openssl = backend
            with open(private_key, 'rb') as fp:
                self.private_key = load_pem_private_key(
                    fp.read(), password=None, backend=self.openssl)

    def secure(self, payload):
        """Return payload secured with random key.

        The return value is in the format expected by the FastSpring
        session variable. That means you can do the following.

        fastspring.render_head(
            webhook=url_for('...'),
            session={
                'reset': True,
                'secure': fastspring.secure({
                    ...
                }),
            })
        """
        key = self.random_key()
        return {
            'payload': self.secure_payload(key, payload),
            'key': self.secure_key(key),
        }

    def random_key(self):
        """Return random AES key."""
        if self.debug:
            return ''
        return urandom(16)

    def secure_payload(self, key, payload):
        """Return payload secured with AES key."""
        if self.debug:
            return payload
        padder = PKCS7(128).padder()
        encryptor = Cipher(AES(key), ECB(), backend=self.openssl).encryptor()
        result = []
        data = json.dumps(payload).encode()
        result.append(encryptor.update(padder.update(data)))
        result.append(encryptor.update(padder.finalize()))
        result.append(encryptor.finalize())
        return b64encode(b''.join(result)).decode()

    def secure_key(self, key):
        """Return AES key secured with RSA private key."""
        if self.debug:
            return key
        result = openssl_private_encrypt(self.private_key, key, self.openssl)
        return b64encode(result).decode()

    def render_head(self, webhook=None, session=None, payload=None):
        html = render_template_string(
            HEAD_TEMPLATE,
            storefront=self.storefront,
            access_key=self.access_key,
            webhook=webhook,
            session=session,
            payload=payload)
        return Markup(html)

    def render_button(self, product):
        t = 'data-fsc-action="Add,Checkout" data-fsc-item-path-value="{}"'
        return Markup(t.format(product))

    def fetch_order(self, order_id):
        return self.fetch('/orders/{}'.format(order_id))

    def fetch_subscription(self, subscription_id):
        return self.fetch('/subscriptions/{}'.format(subscription_id))

    def cancel_subscription(self, subscription_id, immediately=True):
        params = {}
        if immediately:
            params['billingPeriod'] = '0'
        return self.request(
            'DELETE',
            '/subscriptions/{}'.format(subscription_id),
            params=params)

    def fetch(self, uri):
        return self.request('GET', uri)

    def request(self, method, uri, params=None):
        response = requests.request(
            method,
            'https://api.fastspring.com' + uri,
            auth=(self.username, self.password),
            params=params)
        if response.status_code != 200:
            raise APIError(response)
        data = response.json()
        if 'result' in data and data['result'] != 'success':
            raise APIError(response)
        return data


class OrderMixin:

    order_id = Column(Text, primary_key=True)
    reference = Column(Text, nullable=False, unique=True)
    invoice = Column(Text, nullable=False)
    changed = Column(DateTime(timezone=True), nullable=False)
    is_complete = Column(Boolean, default=False, nullable=False)

    @declared_attr
    def data(cls):
        return deferred(Column(JSON, nullable=False))

    def synchronize(self):
        data = current_app.extensions['fastspring'].fetch_order(self.order_id)
        changed = milliseconds_to_datetime(data['changed'])
        if self.changed is not None and self.changed >= changed:
            return False
        self.reference = data['reference']
        self.invoice = data['invoiceUrl']
        self.changed = changed
        self.is_complete = data['completed']
        self.data = data
        return True

    def subscription_item(self):
        candidates = []
        for item in self.data['items']:
            if item.get('subscription'):
                candidates.append(item)
        if len(candidates) != 1:
            return None
        return candidates[0]


class SubscriptionMixin:

    subscription_id = Column(Text, primary_key=True)
    begin = Column(DateTime(timezone=True), nullable=False)
    changed = Column(DateTime(timezone=True), nullable=False)
    next_event = Column(DateTime(timezone=True))
    next_charge = Column(DateTime(timezone=True))
    end = Column(DateTime(timezone=True))
    is_active = Column(Boolean, nullable=False)
    state = Column(Text, nullable=False)

    @declared_attr
    def data(cls):
        return deferred(Column(JSON, nullable=False))

    def synchronize(self):
        data = current_app.extensions['fastspring'].fetch_subscription(self.subscription_id)  # noqa
        changed = milliseconds_to_datetime(data['changed'])
        if self.changed is not None and self.changed >= changed:
            return False
        self.begin = milliseconds_to_datetime(data['begin'])
        self.changed = changed
        self.next_event = milliseconds_to_datetime(data.get('next'))
        self.next_charge = milliseconds_to_datetime(data.get('nextChargeDate'))
        self.end = milliseconds_to_datetime(data.get('end'))
        self.is_active = data['active']
        self.state = data['state']
        self.data = data
        return True

    def cancel(self, immediately=True):
        return current_app.extensions['fastspring'].cancel_subscription(
            self.subscription_id, immediately=immediately)


class APIError(Exception):

    def __init__(self, response):
        self.response = response

    def __str__(self):
        template = 'FastSpring API {} at {} failed with status code {}:\n{}'
        return template.format(
            self.response.request.method,
            self.response.request.url,
            self.response.status_code,
            self.response.text)


def openssl_private_encrypt(key, data, backend):
    """Encrypt data with RSA private key.

    This is a rewrite of the function from PHP, using cryptography
    FFI bindings to the OpenSSL library. Private key encryption is
    non-standard operation and Python packages either don't offer
    it at all, or it's incompatible with the PHP version.

    The backend argument MUST be the OpenSSL cryptography backend.
    """
    length = backend._lib.EVP_PKEY_size(key._evp_pkey)
    buffer = backend._ffi.new('unsigned char[]', length)
    result = backend._lib.RSA_private_encrypt(
        len(data), data, buffer,
        backend._lib.EVP_PKEY_get1_RSA(key._evp_pkey),
        backend._lib.RSA_PKCS1_PADDING)
    backend.openssl_assert(result == length)
    return backend._ffi.buffer(buffer)[:]


UTC = FixedOffsetTimezone(offset=0)


def milliseconds_to_datetime(m):
    if m is None:
        return None
    return datetime.utcfromtimestamp(m / 1000).replace(tzinfo=UTC)


HEAD_TEMPLATE = """\
<script type="text/javascript">
var fscSession = {{ session|tojson }};
{% if webhook %}
var fastspringRedirectUrl;
function fastspringOnPopupWebhookReceived(data) {
  if (!data) return;
  var xhr = new XMLHttpRequest();
  xhr.open("POST", "{{ webhook | safe }}", true);
  xhr.setRequestHeader("Content-Type", "application/json");
  xhr.onreadystatechange = function() {
    if (xhr.readyState === XMLHttpRequest.DONE) {
      if (xhr.status === 200) {
        fastspringRedirectUrl = '{{ request.url | safe }}';
      } else if (xhr.status === 201 || (301 <= xhr.status && xhr.status <= 303)) {
        fastspringRedirectUrl = xhr.getResponseHeader("Location");
      } else {
        var message = "ERROR: Could not process order: " + data["reference"];
        console.log(message);
        alert(message);
        fastspringRedirectUrl = null;
      }
    }
  };
  xhr.send(JSON.stringify({
      "order_id": data["id"],
      "reference": data["reference"],
      "payload": {{ payload|tojson }}
  }));
}
function fastspringOnPopupClosed(data) {
  if (!data) return;
  if (fastspringRedirectUrl) {
    window.location.replace(fastspringRedirectUrl);
  }
}
{% endif %}
</script>
<script
  id="fsc-api"
  src="https://d1f8f9xcsvx3ha.cloudfront.net/sbl/0.7.4/fastspring-builder.min.js"
  type="text/javascript"
  {% if webhook %}
  data-popup-webhook-received="fastspringOnPopupWebhookReceived"
  data-popup-closed="fastspringOnPopupClosed"
  {% endif %}
  {% if access_key %}data-access-key="{{ access_key }}"{% endif %}
  data-storefront="{{ storefront }}">
</script>
"""
