# Intake questionnaire

Ask in this order. Field paths refer to the answers JSON.

## 1. Who is the client?
| Question | Field | Notes |
| --- | --- | --- |
| Is the client an individual or an organization? | `client.type` | `individual` or `organization` |
| Full legal name (as it should appear on documents)? | `client.legal_name` | For entities include the suffix (LLC, Inc.) |
| Preferred name for correspondence? | `client.preferred_name` | optional |
| Best e-mail address? | `client.contact.email` | |
| Best phone number? | `client.contact.phone` | US numbers, any format |
| Preferred contact channel? | `client.contact.preferred_channel` | `email`, `phone`, `portal` |
| Mailing address? | `client.address.*` | `line1`, `line2`, `city`, `state` (2-letter), `postal_code` |

## 2. What is the matter?
| Question | Field | Notes |
| --- | --- | --- |
| Which practice area fits best? | `matter.practice_area` | `estate_planning`, `business_formation`, `contract_review`, `civil_litigation`, `real_estate`, `tax_advisory` |
| In two or three sentences, what do you need help with? | `matter.summary` | min. 20 characters |
| Which state's law applies / where is the matter? | `matter.jurisdiction` | 2-letter code |
| County (if a court or recording office is involved)? | `matter.county` | optional |
| Who is on the other side, if anyone? | `matter.opposing_parties[]` | used for conflict checks |
| How urgent is it? | `matter.urgency` | `routine`, `time_sensitive`, `emergency` |
| Any deadlines we must know about? | `matter.deadlines[]` | `{ "label", "date": "YYYY-MM-DD" }` |

## 3. Engagement terms (ask the firm user, not the client)
| Question | Field | Notes |
| --- | --- | --- |
| Fee arrangement? | `engagement.fee_type` | `flat`, `hourly`, `contingency` |
| Amount | `flat_fee_usd` / `hourly_rate_usd` + `retainer_usd` / `contingency_percent` | required per fee type |
| Responsible professional? | `engagement.responsible_professional` | |

## 4. Compliance
| Question | Field | Notes |
| --- | --- | --- |
| Result of the conflict check? | `conflict_check.status` | `pending`, `cleared`, `flagged`; add `notes` |
| Has the client acknowledged the privacy notice? | `consent.privacy_notice_acknowledged` | must be `true` to proceed |
| May we communicate electronically? | `consent.electronic_communications` | boolean |
| How did the client reach us? | `intake.source` | `web_form`, `phone`, `referral`, `walk_in`, `chat` |
