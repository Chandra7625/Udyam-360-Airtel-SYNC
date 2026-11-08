
import os

FALLBACK = (
    "Based on your business size, location, registration status and budget, "
    "these products are eligible in the supplied catalogue. The bundle "
    "prioritises reliable business connectivity and relevant add-ons. "
    "You can change the selection before checkout."
)


def explain_recommendation(profile, products):
    if products.empty:
        return "No eligible products were found for this business profile."

    api_key = os.getenv("GROQ_API_KEY", "")

    if not api_key:
        return FALLBACK

    try:
        from groq import Groq

        client = Groq(api_key=api_key)

        columns = [
            "product_id",
            "product_name",
            "description",
            "price_min_inr_per_month",
            "price_max_inr_per_month"
        ]

        items = products[columns].to_dict("records")

        prompt = f"""
        You are Udyam360, an expert MSME telecom business advisor.

        Customer profile:
        {profile}

        Eligible products from our catalogue:
        {items}

        Instructions:
        1. Explain why these products suit this business.
        2. Give three short, practical reasons.
        3. Mention one useful caution if relevant.
        4. Do not invent products, prices or benefits.
        5. Use simple, friendly language.
        6. Respond in the customer's preferred language if specified.
        7. Keep the answer concise and easy to understand.
        """

        response = client.chat.completions.create(
            model=os.getenv(
                "GROQ_MODEL",
                "openai/gpt-oss-20b"
            ),
            messages=[
                {
                    "role": "system",
                    "content": "You are the Udyam360 MSME business advisor."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.4,
            max_tokens=500
        )

        answer = response.choices[0].message.content

        return answer if answer else FALLBACK

    except Exception as e:
        print(f"Groq API Error: {type(e).__name__}: {e}")
        return (
            FALLBACK
            + "\n\nAI assistance is temporarily unavailable. "
            "Rule-based recommendations are still active."
        )
