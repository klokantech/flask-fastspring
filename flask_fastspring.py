import requests

from datetime import datetime
from flask import Markup, current_app, render_template_string
from psycopg2.tz import FixedOffsetTimezone
from sqlalchemy import Boolean, Column, DateTime, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import deferred


UTC = FixedOffsetTimezone(offset=0)


class FastSpringAPIError(Exception):

    def __init__(self, response):
        self.response = response

    def __str__(self):
        template = 'FastSpring API {} at {} failed with status code {}:\n{}'
        return template.format(
            self.response.request.method,
            self.response.request.url,
            self.response.status_code,
            self.response.text)


class FastSpring:

    head_template = """\
<script type="text/javascript">
var fscSession = {{ session|tojson }};
{% if webhook %}
function fastspringOnPopupClosed(data) {
  if (!data) return;
  var xhr = new XMLHttpRequest();
  xhr.open("POST", "{{ webhook }}", true);
  xhr.setRequestHeader("Content-Type", "application/json");
  xhr.onreadystatechange = function() {
    if (xhr.readyState === XMLHttpRequest.DONE) {
      if (xhr.status === 200) {
        window.location.replace("{{ request.url }}");
      } else if (xhr.status === 201 || (301 <= xhr.status && xhr.status <= 303)) {
        window.location.replace(xhr.GetResponseHeader("Location"));
      } else {
        var message = "ERROR: Could not process order: " + data["reference"];
        console.log(message);
        alert(message);
      }
    }
  };
  xhr.send(JSON.stringify({
      "order_id": data["id"],
      "reference": data["reference"],
      "payload": {{ payload }}
  }));
}
{% endif %}
</script>
<script
  id="fsc-api"
  src="https://d1f8f9xcsvx3ha.cloudfront.net/sbl/0.7.2/fastspring-builder.min.js"
  type="text/javascript"
  {% if webhook %}data-popup-closed="fastspringOnPopupClosed"{% endif %}
  data-storefront="{{ storefront }}">
</script>"""

    def __init__(self, app=None):
        self.storefront = None
        self.username = None
        self.password = None
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        app.extensions['fastspring'] = self
        self.storefront = app.config['FASTSPRING_STOREFRONT']
        self.username = app.config['FASTSPRING_USERNAME']
        self.password = app.config['FASTSPRING_PASSWORD']

    def render_head(self, webhook=None, session=None, payload=None):
        html = render_template_string(
            self.head_template,
            storefront=self.storefront,
            webhook=webhook,
            session=session,
            payload=payload if payload is not None else 'null')
        return Markup(html)

    def render_button(self, product):
        t = 'data-fsc-action="Add,Checkout" data-fsc-item-path-value="{}"'
        return Markup(t.format(product))

    def fetch_order(self, order_id):
        return self.fetch('/orders/{}'.format(order_id))

    def fetch_subscription(self, subscription_id):
        return self.fetch('/subscriptions/{}'.format(subscription_id))

    def fetch(self, uri):
        response = requests.get(
            'https://api.fastspring.com/{}'.format(uri),
            auth=(self.username, self.password))
        if response.status_code != 200:
            raise FastSpringAPIError(response)
        data = response.json()
        if data['result'] != 'success':
            raise FastSpringAPIError(response)
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


def milliseconds_to_datetime(m):
    if m is None:
        return None
    return datetime.utcfromtimestamp(m / 1000).replace(tzinfo=UTC)
