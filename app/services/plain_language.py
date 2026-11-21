"""Plain-language invoice text for the merchant: English source plus built-in Tamil and Hindi.

Sarvam translates into any supported language when configured. These built-in strings keep the demo
readable offline in the two languages the pilot wedding planner uses most.
"""

REASONS: dict[str, dict[str, str]] = {
    "BANK_CHANGE": {
        "en": "The bank account on this invoice is different from the one verified for this vendor.",
        "ta": "இந்த விலைப்பட்டியலில் உள்ள வங்கிக் கணக்கு, இந்த விற்பனையாளருக்குச் சரிபார்க்கப்பட்ட கணக்கிலிருந்து வேறுபட்டது.",
        "hi": "इस बिल पर दिया बैंक खाता इस विक्रेता के सत्यापित खाते से अलग है।",
    },
    "BANK_UNVERIFIED": {
        "en": "This vendor's bank account has not been verified yet.",
        "ta": "இந்த விற்பனையாளரின் வங்கிக் கணக்கு இன்னும் சரிபார்க்கப்படவில்லை.",
        "hi": "इस विक्रेता का बैंक खाता अभी सत्यापित नहीं हुआ है।",
    },
    "BANK_CHANGED": {
        "en": "The vendor's verified bank account changed after this invoice was checked.",
        "ta": "இந்த விலைப்பட்டியல் சரிபார்க்கப்பட்ட பிறகு விற்பனையாளரின் வங்கிக் கணக்கு மாறியுள்ளது.",
        "hi": "जाँच के बाद विक्रेता का सत्यापित बैंक खाता बदल गया है।",
    },
    "CONFIRMED_DUPLICATE": {
        "en": "This invoice was already received. Paying it again would pay the vendor twice.",
        "ta": "இந்த விலைப்பட்டியல் ஏற்கனவே பெறப்பட்டது. மீண்டும் செலுத்தினால் இருமுறை பணம் செல்லும்.",
        "hi": "यह बिल पहले ही मिल चुका है। दोबारा भुगतान करने से दो बार भुगतान होगा।",
    },
    "POSSIBLE_DUPLICATE": {
        "en": "Another invoice from this vendor has the same date and amount.",
        "ta": "இதே விற்பனையாளரிடமிருந்து இதே தேதி மற்றும் தொகையுடன் மற்றொரு விலைப்பட்டியல் உள்ளது.",
        "hi": "इसी विक्रेता का इसी तारीख़ और राशि का एक और बिल मौजूद है।",
    },
    "ARITHMETIC": {
        "en": "The totals on the invoice do not add up.",
        "ta": "விலைப்பட்டியலில் உள்ள மொத்தத் தொகைகள் கணக்கில் பொருந்தவில்லை.",
        "hi": "बिल के जोड़ सही नहीं बैठते।",
    },
    "MIXED_GST": {
        "en": "IGST is charged together with CGST/SGST, which is not allowed.",
        "ta": "CGST/SGST உடன் IGST சேர்த்து வசூலிக்கப்பட்டுள்ளது; இது அனுமதிக்கப்படாது.",
        "hi": "IGST के साथ CGST/SGST भी लगाया गया है, जो मान्य नहीं है।",
    },
    "ZERO_TOTAL": {
        "en": "The invoice total is zero.",
        "ta": "விலைப்பட்டியல் மொத்தம் பூஜ்ஜியம்.",
        "hi": "बिल की कुल राशि शून्य है।",
    },
    "MISSING_FIELDS": {
        "en": "Some required details are missing from the invoice.",
        "ta": "விலைப்பட்டியலில் சில அவசியமான விவரங்கள் இல்லை.",
        "hi": "बिल में कुछ ज़रूरी जानकारी नहीं है।",
    },
    "LOW_CONFIDENCE": {
        "en": "Some important figures could not be read clearly.",
        "ta": "சில முக்கியமான எண்களைத் தெளிவாகப் படிக்க முடியவில்லை.",
        "hi": "कुछ ज़रूरी आँकड़े साफ़ नहीं पढ़े जा सके।",
    },
    "INSUFFICIENT_CASH": {
        "en": "The amount is more than the cash available right now.",
        "ta": "தொகை தற்போது கையிருப்பில் உள்ள பணத்தை விட அதிகம்.",
        "hi": "राशि अभी उपलब्ध नकद से ज़्यादा है।",
    },
    "CURRENCY_UNSUPPORTED": {
        "en": "The invoice currency is not supported.",
        "ta": "விலைப்பட்டியலின் நாணயம் ஆதரிக்கப்படவில்லை.",
        "hi": "बिल की मुद्रा समर्थित नहीं है।",
    },
    "INVALID_GSTIN": {
        "en": "The GSTIN on the invoice is not valid.",
        "ta": "விலைப்பட்டியலில் உள்ள GSTIN சரியானதல்ல.",
        "hi": "बिल पर दिया GSTIN मान्य नहीं है।",
    },
    "UNKNOWN_VENDOR": {
        "en": "This vendor is not in your vendor list.",
        "ta": "இந்த விற்பனையாளர் உங்கள் விற்பனையாளர் பட்டியலில் இல்லை.",
        "hi": "यह विक्रेता आपकी विक्रेता सूची में नहीं है।",
    },
    "VENDOR_NAME": {
        "en": "The vendor name does not match your records.",
        "ta": "விற்பனையாளர் பெயர் உங்கள் பதிவுகளுடன் பொருந்தவில்லை.",
        "hi": "विक्रेता का नाम आपके रिकॉर्ड से मेल नहीं खाता।",
    },
    "LOW_RATING": {
        "en": "The Prism rating is below 80, so a person should check this invoice before it is paid.",
        "ta": "Prism மதிப்பீடு 80-க்குக் குறைவு; பணம் செலுத்தும் முன் ஒருவர் இதைச் சரிபார்க்க வேண்டும்.",
        "hi": "Prism रेटिंग 80 से कम है, इसलिए भुगतान से पहले किसी व्यक्ति को यह बिल जाँचना चाहिए।",
    },
    "EXTRACTION_FAILED": {
        "en": "The invoice could not be read automatically.",
        "ta": "விலைப்பட்டியலைத் தானாகப் படிக்க முடியவில்லை.",
        "hi": "बिल अपने-आप नहीं पढ़ा जा सका।",
    },
    "DUPLICATE_UPLOAD": {
        "en": "This file repeats an invoice that was already uploaded.",
        "ta": "இது ஏற்கனவே பதிவேற்றப்பட்ட விலைப்பட்டியலின் மறு பதிவேற்றம்.",
        "hi": "यह पहले से अपलोड किए गए बिल को दोहराती फ़ाइल है।",
    },
    "REJECTED": {
        "en": "A reviewer rejected this invoice. It will not be paid.",
        "ta": "ஒரு சரிபார்ப்பாளர் இந்த விலைப்பட்டியலை நிராகரித்தார். இதற்கு பணம் செலுத்தப்படாது.",
        "hi": "समीक्षक ने यह बिल अस्वीकार कर दिया है। इसका भुगतान नहीं होगा।",
    },
}

SUMMARY: dict[str, dict[str, str]] = {
    "en": {
        "sent": "{vendor} sent invoice {number}, dated {date}.",
        "amount": "Amount payable: {amount} for {items} item(s).",
        "deadline": "Pay by {deadline}.",
        "PROCESSED": "All checks passed and the Prism rating is {score}/100. It is ready for payment.",
        "ON_HOLD": "This invoice is on hold (rating {score}/100). Please review it before paying.",
        "REJECTED": "You rejected this invoice. It will not be paid.",
        "unread": "This document could not be read automatically. Please open the original and check it.",
    },
    "ta": {
        "sent": "{vendor} நிறுவனம் {date} தேதியிட்ட {number} எண் விலைப்பட்டியலை அனுப்பியுள்ளது.",
        "amount": "செலுத்த வேண்டிய தொகை: {amount} ({items} பொருட்கள்).",
        "deadline": "{deadline} தேதிக்குள் செலுத்த வேண்டும்.",
        "PROCESSED": "அனைத்துச் சரிபார்ப்புகளும் வெற்றி; Prism மதிப்பீடு {score}/100. பணம் செலுத்தத் தயார்.",
        "ON_HOLD": "இந்த விலைப்பட்டியல் நிறுத்தி வைக்கப்பட்டுள்ளது (மதிப்பீடு {score}/100). பணம் செலுத்தும் முன் சரிபார்க்கவும்.",
        "REJECTED": "நீங்கள் இந்த விலைப்பட்டியலை நிராகரித்தீர்கள். இதற்கு பணம் செலுத்தப்படாது.",
        "unread": "இந்த ஆவணத்தைத் தானாகப் படிக்க முடியவில்லை. மூல ஆவணத்தைத் திறந்து சரிபார்க்கவும்.",
    },
    "hi": {
        "sent": "{vendor} ने {date} का बिल नंबर {number} भेजा है।",
        "amount": "देय राशि: {amount} ({items} आइटम)।",
        "deadline": "{deadline} तक भुगतान करें।",
        "PROCESSED": "सभी जाँच सफल रहीं और Prism रेटिंग {score}/100 है। भुगतान के लिए तैयार।",
        "ON_HOLD": "यह बिल रोका गया है (रेटिंग {score}/100)। भुगतान से पहले कृपया जाँच करें।",
        "REJECTED": "आपने यह बिल अस्वीकार कर दिया है। इसका भुगतान नहीं होगा।",
        "unread": "यह दस्तावेज़ अपने-आप नहीं पढ़ा जा सका। कृपया मूल दस्तावेज़ खोलकर जाँचें।",
    },
}

ITEMS: dict[str, dict[str, str]] = {
    "Wedding lunch, veg thali per plate": {"ta": "திருமண மதிய விருந்து, சைவ சாப்பாடு (ஒரு இலைக்கு)", "hi": "शादी का दोपहर भोज, शाकाहारी थाली (प्रति प्लेट)"},
    "Filter coffee and sweets counter": {"ta": "ஃபில்டர் காபி மற்றும் இனிப்பு கவுண்டர்", "hi": "फ़िल्टर कॉफ़ी और मिठाई काउंटर"},
    "Mandap flower decoration": {"ta": "மண்டப மலர் அலங்காரம்", "hi": "मंडप की फूलों की सजावट"},
    "Jasmine garlands": {"ta": "மல்லிகை மாலைகள்", "hi": "चमेली की मालाएँ"},
    "Bridal mehendi artist": {"ta": "மணப்பெண் மெஹந்தி கலைஞர்", "hi": "दुल्हन की मेहंदी कलाकार"},
    "Guest mehendi, per hand": {"ta": "விருந்தினர் மெஹந்தி, ஒரு கைக்கு", "hi": "मेहमानों की मेहंदी, प्रति हाथ"},
    "Dhol and nadaswaram team": {"ta": "தோல் மற்றும் நாதஸ்வரக் குழு", "hi": "ढोल और नादस्वरम दल"},
    "Candid photography, 2 days": {"ta": "கேண்டிட் புகைப்படம், 2 நாட்கள்", "hi": "कैंडिड फ़ोटोग्राफ़ी, 2 दिन"},
    "Stage lighting and sound": {"ta": "மேடை விளக்கு மற்றும் ஒலி அமைப்பு", "hi": "मंच की रोशनी और साउंड"},
    "Generator rental, per day": {"ta": "ஜெனரேட்டர் வாடகை, ஒரு நாளுக்கு", "hi": "जनरेटर किराया, प्रति दिन"},
    "Printed invitation cards": {"ta": "அச்சிட்ட திருமண அழைப்பிதழ்கள்", "hi": "छपे हुए शादी के निमंत्रण कार्ड"},
    "Envelopes": {"ta": "உறைகள்", "hi": "लिफ़ाफ़े"},
}


def reason_key(code: str) -> str:
    return "ARITHMETIC" if code.startswith("ARITHMETIC_") else code


FIELD_LABELS = {
    "acceptance_date": "acceptance date",
    "written_agreement": "written agreement status",
    "bank_reference": "verified bank reference",
    "gstin": "supplier GSTIN",
    "legal_name": "supplier legal name",
    "lines": "line items",
    "subtotal": "subtotal",
    "cgst": "CGST amount",
    "cgst_rate": "CGST rate",
    "sgst": "SGST amount",
    "sgst_rate": "SGST rate",
    "igst": "IGST amount",
    "igst_rate": "IGST rate",
    "tax_total": "tax total",
    "grand_total": "grand total",
    "total_in_words": "amount in words",
    "invoice_number": "invoice number",
    "invoice_date": "invoice date",
    "amount_minor": "invoice amount",
    "currency": "currency",
    "document_sha256": "document fingerprint",
}
