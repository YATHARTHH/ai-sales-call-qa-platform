"""SQLAlchemy implementation of SaleRepositoryPort."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.application.ports.repositories import SaleRepositoryPort
from packages.domain.retail import (
    Agent,
    Campaign,
    Lead,
    Retailer,
    Sale,
    SaleStatus,
)
from packages.infrastructure.database.models.sales import (
    AgentModel,
    CampaignModel,
    LeadModel,
    RetailerModel,
    SaleModel,
)


class SqlAlchemySaleRepository(SaleRepositoryPort):
    """Persistence adapter for sales, leads, campaigns, and retailers."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save_retailer(self, retailer: Retailer) -> None:
        model = RetailerModel(
            id=retailer.id,
            code=retailer.code,
            name=retailer.name,
            vertical=retailer.vertical,
            is_active=retailer.is_active,
            created_at=retailer.created_at,
        )
        await self._session.merge(model)
        await self._session.flush()

    async def get_retailer(self, retailer_id: str) -> Retailer | None:
        stmt = select(RetailerModel).where(RetailerModel.id == retailer_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if not model:
            return None
        return Retailer(
            id=model.id,
            code=model.code,
            name=model.name,
            vertical=model.vertical,
            is_active=model.is_active,
            created_at=model.created_at,
        )

    async def save_campaign(self, campaign: Campaign) -> None:
        model = CampaignModel(
            id=campaign.id,
            code=campaign.code,
            name=campaign.name,
            channel=campaign.channel,
            is_active=campaign.is_active,
            created_at=campaign.created_at,
        )
        await self._session.merge(model)
        await self._session.flush()

    async def save_agent(self, agent: Agent) -> None:
        model = AgentModel(
            id=agent.id,
            staff_id=agent.staff_id,
            name=agent.name,
            email=agent.email,
            team_lead_id=agent.team_lead_id,
            is_active=agent.is_active,
            created_at=agent.created_at,
        )
        await self._session.merge(model)
        await self._session.flush()

    async def save_lead(self, lead: Lead) -> None:
        model = LeadModel(
            id=lead.id,
            customer_name=lead.customer_name,
            customer_email=lead.customer_email,
            phone=lead.phone,
            suburb=lead.suburb,
            state=lead.state,
            postcode=lead.postcode,
            created_at=lead.created_at,
        )
        await self._session.merge(model)
        await self._session.flush()

    async def get_lead(self, lead_id: str) -> Lead | None:
        stmt = select(LeadModel).where(LeadModel.id == lead_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if not model:
            return None
        return Lead(
            id=model.id,
            customer_name=model.customer_name,
            customer_email=model.customer_email,
            phone=model.phone,
            suburb=model.suburb,
            state=model.state,
            postcode=model.postcode,
            created_at=model.created_at,
        )

    async def save_sale(self, sale: Sale) -> None:
        model = SaleModel(
            id=sale.id,
            lead_id=sale.lead_id,
            retailer_id=sale.retailer_id,
            campaign_id=sale.campaign_id,
            agent_id=sale.agent_id,
            sale_date=sale.sale_date,
            status=sale.status.value,
            product_details=sale.product_details,
            created_at=sale.created_at,
        )
        await self._session.merge(model)
        await self._session.flush()

    async def get_sale(self, sale_id: str) -> Sale | None:
        stmt = select(SaleModel).where(SaleModel.id == sale_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if not model:
            return None
        return Sale(
            id=model.id,
            lead_id=model.lead_id,
            retailer_id=model.retailer_id,
            campaign_id=model.campaign_id,
            agent_id=model.agent_id,
            sale_date=model.sale_date,
            status=SaleStatus(model.status),
            product_details=model.product_details,
            created_at=model.created_at,
        )
