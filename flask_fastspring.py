import requests

from flask import Markup, render_template_string


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
</script>
<script
  id="fsc-api"
  src="https://d1f8f9xcsvx3ha.cloudfront.net/sbl/0.7.2/fastspring-builder.min.js"
  type="text/javascript"
  data-popup-closed="fastspringOnPopupClosed"
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

    def render_head(self, webhook, session=None, payload=None):
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
