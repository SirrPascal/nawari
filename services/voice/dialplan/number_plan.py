"""Kenya Airways Enterprise Numbering Plan & E.164 Normalization Engine."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class ExtensionCategory(str, Enum):
    PRIDE_CENTRE_HQ = "PRIDE_CENTRE_HQ"          # 1000-1999: Headquarters, IT, NOC
    JKIA_TERMINAL_1A = "JKIA_TERMINAL_1A"        # 2000-2999: Airport Terminal 1A, Gates, Check-in
    FLIGHT_OPERATIONS = "FLIGHT_OPERATIONS"      # 3000-3999: Flight Dispatch, Crew, OCC
    REGIONAL_OUTSTATIONS = "REGIONAL_OUTSTATIONS"# 4000-4999: Mombasa, Kisumu, Eldoret
    EXTERNAL_NATIONAL = "EXTERNAL_NATIONAL"      # Kenyan national mobile / fixed (+254)
    EXTERNAL_INTERNATIONAL = "EXTERNAL_INTERNATIONAL" # International numbers
    EMERGENCY = "EMERGENCY"                      # 999, 112, 911 (Protected)
    INVALID = "INVALID"


@dataclass
class NumberPlanInfo:
    raw_number: str
    normalized_number: str
    category: ExtensionCategory
    description: str
    is_emergency: bool = False
    is_allowlisted_test: bool = False
    operator: Optional[str] = None  # Safaricom, Airtel, Telkom, Internal


class KQNumberClassifier:
    """Classifies dialed numbers against the Kenya Airways enterprise dial plan."""

    EMERGENCY_NUMBERS: set[str] = {"999", "112", "911"}
    ALLOWLISTED_TEST_EXTENSIONS: set[str] = {"1001", "1002", "1003", "1004", "4286"}

    @classmethod
    def normalize_number(cls, raw: str) -> str:
        """Strip formatting and normalize local Kenyan numbers to E.164 standard."""
        clean = re.sub(r"[\s\-\(\)\.]", "", raw.strip())

        # Kenyan local 07XX / 01XX to +254...
        if re.match(r"^0(7\d{8}|1\d{8})$", clean):
            return f"+254{clean[1:]}"
        # Kenyan 254... without leading +
        if re.match(r"^254(7\d{8}|1\d{8})$", clean):
            return f"+{clean}"
        return clean

    @classmethod
    def classify(cls, number: str) -> NumberPlanInfo:
        """Classify dialed number into enterprise categories."""
        if not number:
            return NumberPlanInfo("", "", ExtensionCategory.INVALID, "Empty number", False, False, None)

        clean = cls.normalize_number(number)

        # 1. Emergency Numbers (Strict Protection)
        if clean in cls.EMERGENCY_NUMBERS or number.strip() in cls.EMERGENCY_NUMBERS:
            return NumberPlanInfo(
                raw_number=number,
                normalized_number=clean,
                category=ExtensionCategory.EMERGENCY,
                description="Emergency Service Number (Strictly Blocked)",
                is_emergency=True,
                is_allowlisted_test=False,
                operator="EMERGENCY",
            )

        # 2. Allowlisted Test Extensions
        is_test = clean in cls.ALLOWLISTED_TEST_EXTENSIONS

        # 3. Internal 4-digit Extension Ranges
        if re.match(r"^\d{4}$", clean):
            ext_int = int(clean)
            if 1000 <= ext_int <= 1999:
                return NumberPlanInfo(
                    raw_number=number,
                    normalized_number=clean,
                    category=ExtensionCategory.PRIDE_CENTRE_HQ,
                    description="Kenya Airways Pride Centre HQ Extension",
                    is_emergency=False,
                    is_allowlisted_test=is_test,
                    operator="Internal Avaya Aura CM",
                )
            elif 2000 <= ext_int <= 2999:
                return NumberPlanInfo(
                    raw_number=number,
                    normalized_number=clean,
                    category=ExtensionCategory.JKIA_TERMINAL_1A,
                    description="JKIA Airport Terminal 1A Operations Extension",
                    is_emergency=False,
                    is_allowlisted_test=is_test,
                    operator="Internal Avaya Aura CM",
                )
            elif 3000 <= ext_int <= 3999:
                return NumberPlanInfo(
                    raw_number=number,
                    normalized_number=clean,
                    category=ExtensionCategory.FLIGHT_OPERATIONS,
                    description="Flight Operations & Dispatch Hunt Group",
                    is_emergency=False,
                    is_allowlisted_test=is_test,
                    operator="Internal Avaya Aura CM",
                )
            elif 4000 <= ext_int <= 4999:
                return NumberPlanInfo(
                    raw_number=number,
                    normalized_number=clean,
                    category=ExtensionCategory.REGIONAL_OUTSTATIONS,
                    description="Regional Airport Outstation Extension",
                    is_emergency=False,
                    is_allowlisted_test=is_test,
                    operator="Internal Avaya Aura CM",
                )

        # 4. Kenyan National Mobile / Fixed
        if clean.startswith("+254"):
            sub = clean[4:]
            operator = "Kenya Fixed / Other"
            if re.match(r"^(7[0129]|1[1])", sub):
                operator = "Safaricom PLC"
            elif re.match(r"^(7[358]|1[0])", sub):
                operator = "Airtel Kenya"
            elif re.match(r"^77", sub):
                operator = "Telkom Kenya"

            return NumberPlanInfo(
                raw_number=number,
                normalized_number=clean,
                category=ExtensionCategory.EXTERNAL_NATIONAL,
                description=f"Kenyan National Destination ({operator})",
                is_emergency=False,
                is_allowlisted_test=is_test,
                operator=operator,
            )

        # 5. International E.164
        if clean.startswith("+"):
            return NumberPlanInfo(
                raw_number=number,
                normalized_number=clean,
                category=ExtensionCategory.EXTERNAL_INTERNATIONAL,
                description="International Destination",
                is_emergency=False,
                is_allowlisted_test=is_test,
                operator="International Carrier Interconnect",
            )

        return NumberPlanInfo(
            raw_number=number,
            normalized_number=clean,
            category=ExtensionCategory.INVALID,
            description="Unmapped digit pattern outside dial plan",
            is_emergency=False,
            is_allowlisted_test=False,
            operator=None,
        )

