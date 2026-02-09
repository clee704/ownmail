#!/usr/bin/env python3
"""Create encoding test fixtures for CODE_REVIEW.md Section 1."""
import base64
import os

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), '..', 'tests', 'fixtures')

# 1. euc_kr_declared_correctly.eml - Baseline EUC-KR
euc_kr_body = "테스트 이메일입니다. 한글이 정상적으로 표시됩니다.".encode('euc-kr')
euc_kr_correct = (
    b"From: =?euc-kr?B?yMrH2LvzwO4=?= <sender@example.com>\n"
    b"To: recipient@example.com\n"
    b"Subject: =?euc-kr?B?x9G4rrq4IMfRt/K9xQ==?=\n"
    b"Date: Mon, 1 Jan 2024 12:00:00 +0900\n"
    b"Message-ID: <euc-kr-correct@example.com>\n"
    b"Content-Type: text/plain; charset=euc-kr\n\n"
) + euc_kr_body + b"\n"

with open(os.path.join(FIXTURES_DIR, 'euc_kr_declared_correctly.eml'), 'wb') as f:
    f.write(euc_kr_correct)
print("Created euc_kr_declared_correctly.eml")

# 2. euc_kr_declared_as_utf8.eml - Charset mismatch (common from Daum/Hanmail)
mismatch_body = "이 이메일은 EUC-KR로 인코딩되어 있지만 UTF-8이라고 선언되어 있습니다.".encode('euc-kr')
euc_kr_as_utf8 = (
    b"From: sender@daum.net\n"
    b"To: recipient@example.com\n"
    b"Subject: =?euc-kr?B?yMrH2LvzwO4=?=\n"
    b"Date: Tue, 15 Mar 2005 14:30:00 +0900\n"
    b"Message-ID: <charset-mismatch@example.com>\n"
    b"Content-Type: text/plain; charset=utf-8\n\n"
) + mismatch_body + b"\n"

with open(os.path.join(FIXTURES_DIR, 'euc_kr_declared_as_utf8.eml'), 'wb') as f:
    f.write(euc_kr_as_utf8)
print("Created euc_kr_declared_as_utf8.eml")

# 3. cp949_as_euc_kr.eml - CP949 superset issue
# CP949 has characters that EUC-KR doesn't have
cp949_body = "CP949 전용 문자: ㉮㉯㉰㉱㉲㉳ (원 안에 가나다라...)".encode('cp949')
cp949_as_euc_kr = (
    b"From: sender@example.com\n"
    b"To: recipient@example.com\n"
    b"Subject: CP949 Test\n"
    b"Date: Wed, 5 Jun 2008 09:00:00 +0900\n"
    b"Message-ID: <cp949-as-euc-kr@example.com>\n"
    b"Content-Type: text/plain; charset=euc-kr\n\n"
) + cp949_body + b"\n"

with open(os.path.join(FIXTURES_DIR, 'cp949_as_euc_kr.eml'), 'wb') as f:
    f.write(cp949_as_euc_kr)
print("Created cp949_as_euc_kr.eml")

# 4. split_multibyte_rfc2047.eml - Split Korean char across encoded-words
# "한글" in EUC-KR is: \xc7\xd1 \xb1\xdb
# Split the first character across two encoded-words
part1 = base64.b64encode(b'\xc7').decode('ascii')  # First byte of 한
part2 = base64.b64encode(b'\xd1\xb1\xdb').decode('ascii')  # Second byte + 글

split_multi = (
    f"From: sender@example.com\n"
    f"To: recipient@example.com\n"
    f"Subject: =?euc-kr?B?{part1}?= =?euc-kr?B?{part2}?= Test\n"
    f"Date: Thu, 10 Oct 2010 10:10:10 +0900\n"
    f"Message-ID: <split-multibyte@example.com>\n"
    f"Content-Type: text/plain; charset=utf-8\n\n"
    f"This email has a subject with a Korean character split across RFC 2047 encoded-word boundaries.\n"
).encode()

with open(os.path.join(FIXTURES_DIR, 'split_multibyte_rfc2047.eml'), 'wb') as f:
    f.write(split_multi)
print("Created split_multibyte_rfc2047.eml")

# 5. raw_8bit_headers.eml - Raw bytes in headers without RFC 2047
raw_subject = "테스트 제목입니다".encode('euc-kr')
raw_from = "보내는사람".encode('euc-kr')
raw_8bit = (
    b"From: " + raw_from + b" <sender@example.com>\n"
    b"To: recipient@example.com\n"
    b"Subject: " + raw_subject + b"\n"
    b"Date: Fri, 20 Feb 2004 16:45:00 +0900\n"
    b"Message-ID: <raw-8bit@example.com>\n"
    b"Content-Type: text/plain; charset=euc-kr\n\n"
    b"Raw 8-bit headers from old Korean mail clients.\n"
)

with open(os.path.join(FIXTURES_DIR, 'raw_8bit_headers.eml'), 'wb') as f:
    f.write(raw_8bit)
print("Created raw_8bit_headers.eml")

# 6. unknown_charset.eml
unknown_body = "알 수 없는 문자셋으로 선언된 이메일입니다.".encode('euc-kr')
unknown_charset = (
    b"From: sender@example.com\n"
    b"To: recipient@example.com\n"
    b"Subject: Unknown Charset Test\n"
    b"Date: Sat, 1 Mar 2003 08:00:00 +0900\n"
    b'Message-ID: <unknown-charset@example.com>\n'
    b'Content-Type: text/plain; charset="unknown-8bit"\n\n'
) + unknown_body + b"\n"

with open(os.path.join(FIXTURES_DIR, 'unknown_charset.eml'), 'wb') as f:
    f.write(unknown_charset)
print("Created unknown_charset.eml")

# 7. korean_weekday_prefix.eml - Garbled weekday prefix in Date
korean_weekday_name = "월요일".encode('euc-kr')
korean_weekday = (
    b"From: sender@example.com\n"
    b"To: recipient@example.com\n"
    b"Subject: Korean Weekday Test\n"
    b"Date: " + korean_weekday_name + b", 15 Jan 2024 10:30:00 +0900\n"
    b"Message-ID: <korean-weekday@example.com>\n"
    b"Content-Type: text/plain; charset=utf-8\n\n"
    b"Email with Korean weekday name in Date header.\n"
)

with open(os.path.join(FIXTURES_DIR, 'korean_weekday_prefix.eml'), 'wb') as f:
    f.write(korean_weekday)
print("Created korean_weekday_prefix.eml")

# 8. numeric_month_format.eml - Non-standard date format
numeric_date = (
    b"From: sender@example.com\n"
    b"To: recipient@example.com\n"
    b"Subject: Numeric Month Date\n"
    b"Date: 15 1 2024 10:30:00 +9\n"
    b"Message-ID: <numeric-date@example.com>\n"
    b"Content-Type: text/plain; charset=utf-8\n\n"
    b"Email with numeric month and short timezone in Date header.\n"
)

with open(os.path.join(FIXTURES_DIR, 'numeric_month_format.eml'), 'wb') as f:
    f.write(numeric_date)
print("Created numeric_month_format.eml")

# 9. no_date_header.eml - Missing Date, only Received
no_date = (
    b"From: sender@example.com\n"
    b"To: recipient@example.com\n"
    b"Subject: No Date Header\n"
    b"Received: from mail.example.com by mx.example.com; Sun, 21 Jan 2024 14:00:00 +0000\n"
    b"Message-ID: <no-date@example.com>\n"
    b"Content-Type: text/plain; charset=utf-8\n\n"
    b"This email has no Date header. The parser should extract date from Received.\n"
)

with open(os.path.join(FIXTURES_DIR, 'no_date_header.eml'), 'wb') as f:
    f.write(no_date)
print("Created no_date_header.eml")

# 10. truncated_multipart.eml - Incomplete file
truncated = (
    b"From: sender@example.com\n"
    b"To: recipient@example.com\n"
    b"Subject: Truncated Multipart\n"
    b"Date: Mon, 22 Jan 2024 09:00:00 +0000\n"
    b'Message-ID: <truncated@example.com>\n'
    b'Content-Type: multipart/mixed; boundary="BOUNDARY123"\n\n'
    b"--BOUNDARY123\n"
    b"Content-Type: text/plain\n\n"
    b"First part is complete.\n"
    b"--BOUNDARY123\n"
    b"Content-Type: text/plain\n\n"
    b"Second part is trun"  # Intentionally cut off - no closing boundary
)

with open(os.path.join(FIXTURES_DIR, 'truncated_multipart.eml'), 'wb') as f:
    f.write(truncated)
print("Created truncated_multipart.eml")

# 11. nested_rfc822.eml - Forwarded email as attachment
nested = (
    b"From: forwarder@example.com\n"
    b"To: recipient@example.com\n"
    b"Subject: Fwd: Original Subject\n"
    b"Date: Tue, 23 Jan 2024 11:00:00 +0000\n"
    b'Message-ID: <nested-outer@example.com>\n'
    b'Content-Type: multipart/mixed; boundary="OUTER"\n\n'
    b"--OUTER\n"
    b"Content-Type: text/plain\n\n"
    b"See the forwarded email attached.\n"
    b"--OUTER\n"
    b"Content-Type: message/rfc822\n"
    b'Content-Disposition: attachment; filename="forwarded.eml"\n\n'
    b"From: original@example.com\n"
    b"To: forwarder@example.com\n"
    b"Subject: Original Subject\n"
    b"Date: Mon, 22 Jan 2024 10:00:00 +0000\n"
    b"Message-ID: <nested-inner@example.com>\n"
    b"Content-Type: text/plain\n\n"
    b"This is the original email that was forwarded.\n"
    b"--OUTER--\n"
)

with open(os.path.join(FIXTURES_DIR, 'nested_rfc822.eml'), 'wb') as f:
    f.write(nested)
print("Created nested_rfc822.eml")

# 12. mixed_charset_parts.eml - Different charsets per part
euc_kr_part = "이 부분은 charset 선언이 없지만 EUC-KR입니다.".encode('euc-kr')
utf8_part = "This part is in UTF-8: 안녕하세요\n".encode()
mixed_charset = (
    b"From: sender@example.com\n"
    b"To: recipient@example.com\n"
    b"Subject: Mixed Charset Parts\n"
    b"Date: Wed, 24 Jan 2024 12:00:00 +0000\n"
    b'Message-ID: <mixed-charset@example.com>\n'
    b'Content-Type: multipart/alternative; boundary="MIXED"\n\n'
    b"--MIXED\n"
    b"Content-Type: text/plain; charset=utf-8\n\n"
) + utf8_part + (
    b"--MIXED\n"
    b"Content-Type: text/plain\n\n"
) + euc_kr_part + b"\n--MIXED--\n"

with open(os.path.join(FIXTURES_DIR, 'mixed_charset_parts.eml'), 'wb') as f:
    f.write(mixed_charset)
print("Created mixed_charset_parts.eml")

# 13. mostly_readable.eml - 90%+ readable with some corruption
mostly = (
    b"From: sender@example.com\n"
    b"To: recipient@example.com\n"
    b"Subject: Mostly Readable\n"
    b"Date: Thu, 25 Jan 2024 13:00:00 +0000\n"
    b"Message-ID: <mostly-readable@example.com>\n"
    b"Content-Type: text/plain; charset=utf-8\n\n"
    b"This email is mostly readable with valid UTF-8 content.\n"
    b"Here is some normal text that should decode fine.\n"
    b"But here are some bad bytes: \xff\xfe that don't decode.\n"
    b"Back to normal readable text again.\n"
    b"More readable content here to ensure we hit 90%+ readable ratio.\n"
    b"The parser should accept this despite the few corrupted bytes.\n"
)

with open(os.path.join(FIXTURES_DIR, 'mostly_readable.eml'), 'wb') as f:
    f.write(mostly)
print("Created mostly_readable.eml")

print("\n=== All 13 fixtures created! ===")
