from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import (
    Certificate,
    CertificateStatus,
    CertificateVerificationLog,
    InternshipBatch,
    InternshipDomain,
    PublishStatus,
)
from app.schemas.internship import BatchOut, CertificateOut, DomainOut
from app.services.aggregate import batch_out, certificate_out, domain_out

router = APIRouter(tags=["public"])


@router.get("/internship-domains", response_model=list[DomainOut])
def list_domains(status_filter: str | None = None, db: Session = Depends(get_db)):
    query = select(InternshipDomain)
    if status_filter != "all":
        query = query.where(InternshipDomain.status == PublishStatus.ACTIVE)
    domains = db.scalars(
        query.order_by(InternshipDomain.display_order, InternshipDomain.title)
    )
    return [domain_out(db, d) for d in domains]


@router.get("/internship-domains/{slug}", response_model=DomainOut)
def get_domain(slug: str, db: Session = Depends(get_db)):
    domain = db.scalar(select(InternshipDomain).where(InternshipDomain.slug == slug))
    if domain is None:
        raise HTTPException(status_code=404, detail="Internship domain not found")
    return domain_out(db, domain)


@router.get("/internship-batches", response_model=list[BatchOut])
def list_batches(domain_id: str | None = None, db: Session = Depends(get_db)):
    query = select(InternshipBatch)
    if domain_id:
        query = query.where(InternshipBatch.domain_id == domain_id)
    return [batch_out(db, b) for b in db.scalars(query.order_by(InternshipBatch.start_date))]


@router.get("/certificates/verify/{certificate_number}", response_model=CertificateOut)
def verify_certificate(
    certificate_number: str, request: Request, db: Session = Depends(get_db)
):
    """Public — no authentication. Every attempt is logged."""
    number = certificate_number.strip().upper()

    certificate = db.scalar(
        select(Certificate).where(
            Certificate.certificate_number == number,
            Certificate.status == CertificateStatus.ISSUED,
        )
    )

    forwarded = request.headers.get("x-forwarded-for")
    ip = (
        forwarded.split(",")[0].strip()
        if forwarded
        else (request.client.host if request.client else None)
    )

    db.add(
        CertificateVerificationLog(
            certificate_id=certificate.id if certificate else None,
            queried_number=number,
            found=certificate is not None,
            ip_address=ip,
            user_agent=request.headers.get("user-agent", "")[:255] or None,
        )
    )
    db.commit()

    if certificate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Certificate not found"
        )

    return certificate_out(db, certificate)


@router.get("/health")
def health():
    return {"status": "ok"}
