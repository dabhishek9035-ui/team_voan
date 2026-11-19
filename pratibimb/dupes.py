"""B3. Duplicate detection, three layers kept separate.

semantic     normalised ticket_id / utr / order_id / qr_payload   strongest
exact_file   identical sha256                                     exact resend
perceptual   phash/ahash within a Hamming threshold               similarity only: a SIGNAL, never a conclusion

A shared identifier between two DIFFERENT screenshot types of the same traveller (UPI success + bank SMS)
is corroboration, not a duplicate. The same identifier from a different traveller is always reported.
Flags are computed from the immutable records on demand; nothing is stored or mutated.
"""
from . import views as vw


def _earlier(store, evidence_id, trip_id=None):
    """Evidence submitted before `evidence_id`, in ingest order, with current interpretations."""
    out = []
    for it in vw.items(store):
        if it["ev"]["evidence_id"] == evidence_id:
            break
        out.append(it)
    return out


def detect(store, interp_id, cfg):
    me = next((i for i in vw.items(store) if i["id"] == interp_id), None)
    if me is None:
        return []
    my_ids = vw.ids_of(me)
    flags = []
    for other in _earlier(store, me["ev"]["evidence_id"]):
        o_ids = vw.ids_of(other)
        same_sender = other["ev"]["sender_id"] == me["ev"]["sender_id"]
        same_type = other["interp"]["screenshot_type"] == me["interp"]["screenshot_type"]
        layers, matched = [], []
        shared = sorted(k for k in my_ids if my_ids[k] and my_ids[k] == o_ids[k])
        if shared and (not same_sender or same_type):
            layers.append("semantic")
            matched = shared
        if me["ev"]["sha256"] == other["ev"]["sha256"]:
            layers.append("exact_file")
        d_p = vw.hamming(me["ev"]["phash"], other["ev"]["phash"])
        d_a = vw.hamming(me["ev"]["ahash"], other["ev"]["ahash"])
        perceptual = ((d_p is not None and d_p <= cfg["phash_hamming_threshold"]) or
                      (d_a is not None and d_a <= cfg["ahash_hamming_threshold"]))
        if perceptual:
            layers.append("perceptual")
        if not layers:
            continue
        flags.append({
            "item": me["ev"]["evidence_id"], "item_interp": interp_id,
            "earlier": other["ev"]["evidence_id"], "earlier_interp": other["id"],
            "layers": layers, "matched_identifiers": matched, "same_sender": same_sender,
            "earlier_sender": other["ev"]["sender_id"], "earlier_received_at": other["ev"]["received_at"],
            "phash_distance": d_p, "ahash_distance": d_a,
            "kind": ("resend_same_sender" if same_sender else "same_item_other_sender")
                    if ("semantic" in layers or "exact_file" in layers) else "looks_similar_only",
            "strength": "identifier" if "semantic" in layers else ("file" if "exact_file" in layers else "similarity_only"),
            "plain_reason": _reason(layers, same_sender, other, d_p),
        })
    return flags


def _reason(layers, same_sender, other, d):
    who = "the same sender" if same_sender else "a different sender"
    if "semantic" in layers or "exact_file" in layers:
        return (f"The same item was already submitted by {who} on {other['ev']['received_at']} "
                f"(evidence {other['ev']['evidence_id']}).")
    return (f"Looks similar to evidence {other['ev']['evidence_id']} from {who} (image distance {d}). "
            "Similarity is a hint only and needs an identifier match or a human check.")
