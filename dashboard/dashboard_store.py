from datetime import datetime, timezone
from conversation import _connect, _lock

def _rows(sql, args=()):
    with _lock:
        with _connect() as conn:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]

def leads(channel):
    product = "AI Intensive Bootcamp" if channel == "B2C" else "AI Corporate Training"
    return _rows("""
        SELECT l.*, p.infographic_sent, p.class_link_sent_for,
               p.registration_doc_sent, p.registration_confirmed,
               p.payment_claimed, p.proposal_sent, p.meeting_request,
               p.updated_at AS flow_updated_at
        FROM leads l
        LEFT JOIN program_flow_state p ON p.sender=l.sender
        WHERE l.product_interest=?
        ORDER BY COALESCE(l.updated_at, l.created_at) DESC
    """, (product,))

def lead(sender):
    rows = _rows("""
        SELECT l.*, p.infographic_sent, p.class_link_sent_for,
               p.registration_doc_sent, p.registration_confirmed,
               p.payment_claimed, p.proposal_sent, p.meeting_request,
               p.updated_at AS flow_updated_at
        FROM leads l
        LEFT JOIN program_flow_state p ON p.sender=l.sender
        WHERE l.sender=?
    """, (sender,))
    return rows[0] if rows else None

def conversation(sender, limit=80):
    # conversation_messages schema from the WhatsApp service.
    rows = _rows("""
        SELECT role, content, created_at
        FROM conversation_messages
        WHERE sender=?
        ORDER BY id DESC LIMIT ?
    """, (sender, limit))
    return list(reversed(rows))

def followup(sender):
    rows = _rows("""
        SELECT kind, due_at, scheduled_at, sent_at
        FROM followups WHERE sender=?
    """, (sender,))
    return rows[0] if rows else None

def summary(channel):
    ls = leads(channel)
    total = len(ls)

    if channel == "B2C":
        selected = sum(1 for x in ls if x.get("selected_class"))
        registered = sum(1 for x in ls if x.get("registration_confirmed"))
        payment = sum(1 for x in ls if x.get("payment_claimed"))
        funnel = [
            {"label": "Total Leads", "value": total},
            {"label": "Selected Class", "value": selected},
            {"label": "Registration Confirmed", "value": registered},
            {"label": "Payment Confirmation", "value": payment},
        ]
        breakdown = [
            {"label": "ML", "value": sum(1 for x in ls if x.get("selected_class") == "ML")},
            {"label": "CV", "value": sum(1 for x in ls if x.get("selected_class") == "CV")},
            {"label": "NLP", "value": sum(1 for x in ls if x.get("selected_class") == "NLP")},
            {"label": "Unknown", "value": sum(1 for x in ls if not x.get("selected_class"))},
        ]
        progressed = registered
    else:
        qualified = sum(1 for x in ls if x.get("company_name") and x.get("participant_count") and x.get("preferred_delivery") and x.get("training_goal"))
        proposal = sum(1 for x in ls if x.get("proposal_sent"))
        meeting = sum(1 for x in ls if x.get("meeting_request"))
        funnel = [
            {"label": "Total Leads", "value": total},
            {"label": "Qualified", "value": qualified},
            {"label": "Proposal Sent", "value": proposal},
            {"label": "Meeting Requested", "value": meeting},
        ]
        goals = ["Generative AI Tools", "AI Engineering"]
        breakdown = [
            {"label": g, "value": sum(1 for x in ls if (x.get("training_goal") or "").lower() == g.lower())} for g in goals
        ]
        known = sum(x["value"] for x in breakdown)
        other = sum(1 for x in ls if x.get("training_goal")) - known
        breakdown += [{"label": "Other", "value": max(0, other)}, {"label": "Unknown", "value": sum(1 for x in ls if not x.get("training_goal"))}]
        progressed = proposal

    def recent_count(days=None):
        now = datetime.now(timezone.utc)
        count = 0
        for x in ls:
            raw = x.get("created_at")
            if not raw:
                continue
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if days is None:
                    if dt.date() == now.date(): count += 1
                elif (now - dt).total_seconds() <= days * 86400:
                    count += 1
            except (ValueError, TypeError):
                pass
        return count

    return {
        "total": total,
        "progressed": progressed,
        "funnel": funnel,
        "breakdown": breakdown,
        "recent": {"today": recent_count(), "week": recent_count(7), "month": recent_count(30)},
    }


def api_usage(sender):
    from usage_store import usage_summary
    return usage_summary(sender)
