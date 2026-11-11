# WAservix for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![tests](https://github.com/TekservixHQ/ha-waservix/actions/workflows/tests.yml/badge.svg)](https://github.com/TekservixHQ/ha-waservix/actions/workflows/tests.yml)

Send WhatsApp alerts from Home Assistant using your own WhatsApp number with [WAservix](https://tekservix.com/waservix/), and trigger automations when a WhatsApp message arrives.

WAservix links your number by QR code (the same way WhatsApp Web does) and gives you an API, so Home Assistant can send camera snapshots, reports and alerts to you, your family or a WhatsApp group, and react to messages like "STATUS" or "LIGHTS OFF".

## What you get

- **Notify entity**: use `notify.send_message` to message your default number or group
- **`waservix.send_message` action**: text, image (for example a camera snapshot) or document to any number or group
- **Incoming message events**: `waservix_message_received` with `from`, `message` and `group`
- **Other events**: `waservix_event` for status updates, reactions, calls and session changes
- Requests are checked against your number's webhook secret

## Requirements

- A Tekservix account with WAservix, your number linked by QR code, and its API key (Devices in the dashboard)
- For incoming messages: Home Assistant reachable from the internet (Home Assistant Cloud, or your own domain set as the external URL). Sending works without it.

## Install

1. In HACS, open the menu → **Custom repositories**, add `https://github.com/TekservixHQ/ha-waservix` with type **Integration**.
2. Install **WAservix** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → WAservix** and enter the API key of your number, an optional default recipient (number or group JID), and the number's webhook secret.
4. A notification shows your Home Assistant webhook URL: paste it as the webhook of your number in the WAservix dashboard (Devices → your number → Webhook) and choose the events to send.

## Examples

Send a camera snapshot when the doorbell rings:

```yaml
automation:
  - alias: "Doorbell snapshot on WhatsApp"
    triggers:
      - trigger: state
        entity_id: binary_sensor.doorbell
        to: "on"
    actions:
      - action: waservix.send_message
        data:
          to: "+15551234567"
          message: "Someone is at the door"
          image_url: "https://my-home.example.com/local/snapshots/door.jpg"
```

Alert the family group:

```yaml
- action: notify.send_message
  target:
    entity_id: notify.waservix
  data:
    title: "Leak"
    message: "Water detected under the kitchen sink"
```

Answer a WhatsApp command:

```yaml
automation:
  - alias: "WhatsApp STATUS command"
    triggers:
      - trigger: event
        event_type: waservix_message_received
    conditions:
      - condition: template
        value_template: "{{ trigger.event.data.message | trim | upper == 'STATUS' and not trigger.event.data.group }}"
    actions:
      - action: waservix.send_message
        data:
          to: "{{ trigger.event.data.from }}"
          message: "Alarm: {{ states('alarm_control_panel.home') }}"
```

Only act on messages from numbers you trust: check `trigger.event.data.from` in the condition.

WAservix is not Meta's official WhatsApp Business Platform: WhatsApp's spam rules apply to your number, so only message people who expect to hear from you.

## More from Tekservix

- [SMS Gora for Home Assistant](https://github.com/TekservixHQ/ha-smsgora): SMS alerts through your own Android phones, no internet needed on the receiving side
- [AI Sales Agent](https://tekservix.com/ai-sales-agent) and [Website to App](https://tekservix.com/mobile-apps)
- WAservix libraries for many languages: [github.com/TekservixHQ](https://github.com/TekservixHQ)

## License

MIT
