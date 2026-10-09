# Engagement Letter and Service Agreement

**{{ firm.name }}**
{{ firm.address }} · {{ firm.phone }} · {{ firm.email }}

{{ today | longdate }}

{{ client.legal_name }}
{{ client.address.line1 }}
{% if client.address.line2 %}
{{ client.address.line2 }}
{% endif %}
{{ client.address.city }}, {{ client.address.state }} {{ client.address.postal_code }}

Re: {{ matter.practice_area | title }} — Engagement Terms (Client ID {{ client_id }})

Dear {{ client.salutation }}:

Thank you for selecting {{ firm.name }} (the "Firm"). This letter confirms the terms on which the Firm will represent {{ client.legal_name }} ("you" or the "Client").

## 1. Scope of Engagement

The Firm will provide the following services: {{ matter.summary }}

Services outside this scope, including appeals, new matters or related disputes, require a separate written agreement or a written amendment to this letter.

{% if matter.opposing_parties %}
For conflict-of-interest purposes, you have identified other parties to this matter ({{ matter.opposing_parties | join }}).
{% endif %}

## 2. Responsible Professional

{{ engagement.responsible_professional }} will have primary responsibility for your matter and may delegate tasks to other Firm personnel under appropriate supervision.

## 3. Fees and Billing

{% if engagement.fee_type == "hourly" %}
- Fees are charged at {{ engagement.hourly_rate_usd | money }} per hour, billed in {{ firm.billing_increment_minutes }}-minute increments.
- Before work begins you agree to deposit a retainer of {{ engagement.retainer_usd | money }}, which will be held in the Firm's {{ jurisdiction.trust_account_name }} and applied to invoices as they are issued.
- Invoices are issued monthly and are due within 30 days.
{% endif %}
{% if engagement.fee_type == "flat" %}
- The Firm will perform the services described above for a flat fee of {{ engagement.flat_fee_usd | money }}.
- The flat fee is due at signing and covers only the scope described in Section 1.
{% endif %}
{% if engagement.fee_type == "contingency" %}
- The Firm's fee is {{ engagement.contingency_percent }}% of any gross recovery.
- If there is no recovery, you will not owe a fee, but you remain responsible for out-of-pocket costs as described below.
{% endif %}
- Out-of-pocket costs (filing fees, courier, records) are billed at cost without markup.

## 4. Communications

{% if consent.electronic_communications %}
You have agreed that the Firm may communicate with you by e-mail at {{ client.contact.email }}. Unencrypted e-mail carries some risk of interception; tell us if you want a different channel for sensitive information.
{% endif %}
{% if not consent.electronic_communications %}
You have asked that the Firm not use e-mail for substantive communications. The Firm will contact you by phone at {{ client.contact.phone }} or by mail.
{% endif %}

## 5. Fee Disputes

{{ jurisdiction.fee_dispute_notice }}

## 6. File Retention

The Firm will retain your file for {{ jurisdiction.record_retention_years }} years after the matter closes, after which it may be destroyed without further notice unless you request its return in writing.

## 7. Governing Law and Signatures

{{ jurisdiction.governing_law }} {{ jurisdiction.e_signature_note }}

If these terms are acceptable, please sign below and return a copy to the Firm.

Sincerely,

{{ engagement.responsible_professional }}
{{ firm.name }}

**Accepted and agreed:**

______________________________
{{ client.legal_name }}

Date: ________________________
