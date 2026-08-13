from pydantic import BaseModel, Field


class PlatformSettingsOut(BaseModel):
    """
    Bounds travel with the value so the console can validate before it submits
    and render the same limits the API enforces.
    """

    certificate_fee_paise: int
    min_fee_paise: int
    max_fee_paise: int


class UpdateCertificateFeeRequest(BaseModel):
    # In paise, matching Razorpay — 5000 is ₹50. The console converts, so the
    # wire format never carries a fractional rupee.
    amount_paise: int = Field(ge=100, le=5_000_000)
