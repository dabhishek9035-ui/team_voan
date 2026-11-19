"""Adaptive challenge selection and the explicit no-response path."""
REQUESTS = {
    "utr": "bank_sms",
    "order_id": "payment_app_history",
    "ticket_id": "ticket_with_status_bar_and_time",
    "timestamp": "payment_app_history",
}


def choose_request(assessment):
    for signal in assessment.get("signals", []):
        if signal["name"] == "unreadable_key_field":
            field = signal["plain_reason"].split(" ", 1)[0]
            return REQUESTS.get(field, "bank_sms"), signal["plain_reason"]
    if assessment.get("decision_support") in ("needs_review", "insufficient"):
        return "bank_sms", "no second source for this payment"
    return None


def request_challenge(store, subject_ref, assessment, trip_id=None):
    choice = choose_request(assessment)
    if choice is None:
        return None
    request_type, reason = choice
    return store.add_challenge(subject_ref, request_type, reason, trip_id)


def record_no_response(store, challenge_id):
    store.respond_challenge(challenge_id, responded=False)
