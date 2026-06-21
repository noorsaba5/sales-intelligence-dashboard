"""
Stripe -> Supabase plan sync webhook.

Deploy this separately from Streamlit, for example on Render or Railway.

Required environment variables:
- STRIPE_SECRET_KEY
- STRIPE_WEBHOOK_SECRET
- SUPABASE_URL
- SUPABASE_SERVICE_ROLE_KEY

Recommended Stripe setup:
1. Use Payment Links or Checkout.
2. Your Streamlit upgrade buttons must append client_reference_id=<supabase_user_id>.
3. Put real Stripe Price IDs in PRICE_ID_TO_PLAN below.
4. Add webhook endpoint:
   https://YOUR-WEBHOOK-SERVICE.onrender.com/stripe/webhook
5. Subscribe to:
   - checkout.session.completed
   - customer.subscription.updated
   - customer.subscription.deleted
   - invoice.payment_failed
"""

import os
import logging
from typing import Optional

import stripe
from fastapi import FastAPI, Request, HTTPException
from supabase import create_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("stripe_webhook")

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

supabase_admin = None
if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
    supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

app = FastAPI(title="Stripe Supabase Plan Webhook")

# IMPORTANT:
# Replace these placeholders with your real Stripe Price IDs.
# Example:
# PRICE_ID_TO_PLAN = {
#     "price_1ABCstarter": "starter",
#     "price_1ABCpro": "pro",
#     "price_1ABCpremium": "premium",
# }
PRICE_ID_TO_PLAN = {
    "https://buy.stripe.com/test_4gM6oI7AC6rVfX1fEY4Vy00": "starter",
    "https://buy.stripe.com/test_6oU7sM5sucQjh152Sc4Vy02": "pro",
    "https://buy.stripe.com/test_9B6fZi8EG4jN4ej3Wg4Vy03": "premium",
}


def require_config() -> None:
    missing = []
    if not STRIPE_SECRET_KEY:
        missing.append("STRIPE_SECRET_KEY")
    if not STRIPE_WEBHOOK_SECRET:
        missing.append("STRIPE_WEBHOOK_SECRET")
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_SERVICE_ROLE_KEY:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if supabase_admin is None:
        missing.append("Supabase client")

    if missing:
        raise RuntimeError(f"Missing webhook configuration: {', '.join(missing)}")


def normalise_plan(plan: Optional[str]) -> str:
    plan = (plan or "starter").strip().lower()
    return plan if plan in {"starter", "pro", "premium"} else "starter"


def update_profile_plan(user_id: str, plan: str) -> bool:
    """Update Supabase profiles.plan using the Supabase Auth user id."""
    if not user_id:
        logger.warning("No user_id supplied; cannot update profile plan.")
        return False

    plan = normalise_plan(plan)

    try:
        result = (
            supabase_admin
            .table("profiles")
            .update({"plan": plan})
            .eq("id", user_id)
            .execute()
        )
        logger.info("Updated Supabase profile %s -> %s", user_id, plan)
        return True
    except Exception as exc:
        logger.exception("Failed to update Supabase profile %s -> %s: %s", user_id, plan, exc)
        return False


def price_id_to_plan(price_id: Optional[str]) -> str:
    if not price_id:
        return "starter"
    return normalise_plan(PRICE_ID_TO_PLAN.get(price_id, "starter"))


def plan_from_subscription(subscription) -> str:
    """Find plan from a Stripe Subscription object."""
    try:
        price_id = subscription["items"]["data"][0]["price"]["id"]
        return price_id_to_plan(price_id)
    except Exception as exc:
        logger.warning("Could not determine plan from subscription: %s", exc)
        return "starter"


def plan_from_checkout_session(session) -> str:
    """
    Find plan from a Checkout Session.
    Works for subscription mode and many Payment Link flows.
    """
    # Best case: subscription checkout.
    subscription_id = session.get("subscription")
    if subscription_id:
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            return plan_from_subscription(subscription)
        except Exception as exc:
            logger.warning("Could not retrieve subscription %s: %s", subscription_id, exc)

    # Fallback: inspect line items from the checkout session.
    session_id = session.get("id")
    if session_id:
        try:
            line_items = stripe.checkout.Session.list_line_items(session_id, limit=5)
            for item in line_items.get("data", []):
                price_id = item.get("price", {}).get("id")
                plan = PRICE_ID_TO_PLAN.get(price_id)
                if plan:
                    return normalise_plan(plan)
        except Exception as exc:
            logger.warning("Could not list line items for session %s: %s", session_id, exc)

    # Last fallback: allow Stripe metadata to specify plan.
    metadata_plan = (session.get("metadata") or {}).get("plan")
    return normalise_plan(metadata_plan)


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    try:
        require_config()
    except RuntimeError as exc:
        logger.error(str(exc))
        raise HTTPException(status_code=500, detail="Webhook is not configured correctly.")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            STRIPE_WEBHOOK_SECRET,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event["type"]
    obj = event["data"]["object"]

    logger.info("Received Stripe event: %s", event_type)

    if event_type == "checkout.session.completed":
        user_id = obj.get("client_reference_id")
        plan = plan_from_checkout_session(obj)

        if not user_id:
            logger.warning(
                "checkout.session.completed has no client_reference_id. "
                "Check your Streamlit upgrade links."
            )
            return {"status": "ignored", "reason": "missing client_reference_id"}

        updated = update_profile_plan(user_id, plan)
        return {"status": "ok" if updated else "failed", "plan": plan}

    if event_type == "customer.subscription.updated":
        # This event does not always contain client_reference_id.
        # For a production version, store stripe_customer_id on profiles.
        status = obj.get("status")
        plan = plan_from_subscription(obj)
        if status not in {"active", "trialing"}:
            plan = "starter"

        logger.info(
            "Subscription updated. Plan calculated as %s, but no direct Supabase user_id is available "
            "unless stripe_customer_id is stored in profiles.",
            plan,
        )
        return {"status": "received", "note": "store stripe_customer_id for automatic subscription updates"}

    if event_type in {"customer.subscription.deleted", "invoice.payment_failed"}:
        logger.info(
            "%s received. To downgrade automatically, store stripe_customer_id on profiles.",
            event_type,
        )
        return {"status": "received", "note": "store stripe_customer_id for automatic downgrade"}

    return {"status": "ignored", "event_type": event_type}


@app.get("/healthz")
async def healthz():
    configured = bool(
        STRIPE_SECRET_KEY
        and STRIPE_WEBHOOK_SECRET
        and SUPABASE_URL
        and SUPABASE_SERVICE_ROLE_KEY
        and supabase_admin is not None
    )
    return {"status": "ok", "configured": configured}
