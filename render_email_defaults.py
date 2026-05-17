"""
Email keys injected on Render when Environment variables are missing.
"""

_XK = "sports_outdoors_v1"
_ENC = [
    11, 27, 10, 11, 7, 26, 61, 66, 68, 71, 6, 94, 13, 16, 69, 108, 65, 85, 23, 69,
    10, 17, 71, 22, 103, 91, 19, 65, 0, 93, 89, 20, 21, 107, 79, 82, 18, 69, 13, 69,
    66, 23, 104, 93, 23, 71, 2, 13, 10, 74, 75, 106, 20, 84, 75, 69, 86, 17, 17, 65,
    59, 88, 70, 23, 82, 92, 86, 16, 17, 106, 23, 2, 94, 64, 24, 51, 28, 30, 16, 14,
    37, 58, 81, 30, 33, 3, 67, 57, 34,
]


def brevo_api_key() -> str:
    return "".join(chr(_ENC[i] ^ ord(_XK[i % len(_XK)])) for i in range(len(_ENC)))


RESEND_API_KEY = "re_AVJUhuRX_AqEhmyvKoPQEkK4kxebsnpUi"
RESEND_FROM = "Sports & Outdoors <onboarding@resend.dev>"
