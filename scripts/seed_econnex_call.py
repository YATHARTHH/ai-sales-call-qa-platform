"""Seed the official 6-page Redacted Call Transcript into SalesCall QA Platform.

Call Details:
- Campaign: Outbound Internet Plan Comparator (Econnex / Equinix Comparison)
- Retailer: [PROVIDER_A] (NBN 25/8.5 Value Plan)
- Customer: [CUSTOMER_FULL_NAME] (Missus [CUSTOMER_NAME])
- Existing Provider: iPrimus ($65/mo)
- Sold Product: NBN 25/8.5 Mbps ($42.90 for first 6 months, then $72.90 regular price, month-to-month, free NetComm CF40 Wi-Fi 6 modem)
- Key Audit Findings:
  1. Recording Disclosure (Page 2) - PASS
  2. NBN Key Fact Sheet Peak Speeds 25/8.5 Mbps 7-11 PM (Page 3) - PASS
  3. Promo Pricing $42.90 vs Regular $72.90 (Page 2, 3) - PASS
  4. Script Misstatement "six weeks" instead of six months (Page 2) - WARN
  5. Total Minimum Cost Discrepancy: $317 form vs $42.90 verbal guarantee (Page 5) - REVIEW_REQUIRED
  6. PCI-DSS Recording Mute Protocol before card payment (Page 4) - PASS
  7. Delivery Address Manual Workaround Risk (Page 5, 6) - AUDIT_NOTE
  8. Explicit Informed Consent & OTP Verification (Page 6) - PASS
"""

import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, datetime

# Add repository root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import packages.infrastructure.database.models  # noqa: F401
from packages.domain.check_library import CheckDefinition, CheckType, CheckVersion
from packages.domain.evaluation import (
    CheckOutcome,
    EvaluationResult,
    EvaluationRun,
    EvaluationRunStatus,
    Evidence,
    EvidenceType,
    GateDecision,
)
from packages.domain.provenance import AIProvenance
from packages.domain.retail import Agent, Campaign, Lead, Retailer, Sale
from packages.domain.state import GateStatus
from packages.domain.transcript import Recording, SpeakerType, Transcript, TranscriptSegment
from packages.infrastructure.config.settings import settings
from packages.infrastructure.database.base import Base
from packages.infrastructure.database.models.artifacts import ArtifactModel
from packages.infrastructure.database.repositories import (
    SqlAlchemyCheckLibraryRepository,
    SqlAlchemyEvaluationRepository,
    SqlAlchemySaleRepository,
    SqlAlchemyTranscriptRepository,
)


RAW_TRANSCRIPT_PAGES = [
    # Page 1
    (SpeakerType.CUSTOMER, 0, 3000, "Hello. [CUSTOMER_NAME] speaking."),
    (SpeakerType.AGENT, 3500, 9000, "Yes. Hi, [CUSTOMER_NAME]. Good day. This is [AGENT_NAME] from Internet's comparison. How are you?"),
    (SpeakerType.CUSTOMER, 9500, 11500, "Good. Thanks. How are you?"),
    # Page 2
    (
        SpeakerType.AGENT,
        12000,
        38000,
        "Yeah. I'm good. Thank you. And we noticed that you're looking for better Internet plans, and we're calling to assist you with this. Yeah. K. And as I check it, your address is [SERVICE_ADDRESS] Correct. [UNCLEAR_NAME]. Yep. [SERVICE_ADDRESS]. K. By the way, please be advised that this call will be recorded for quality assuranceand, training purposes. K? Nowlet me double check the address. Bear with me. There you go. As I check it yeah. The address is already an NBN ready, fiber to the premises technology. Okay? Now just to ask, [CUSTOMER_NAME], who's your current Internet service provider? Do you have one? IPRIMUS. You are currently with iPRIMUS. How much are you paying?",
    ),
    (SpeakerType.CUSTOMER, 39000, 42000, "They reduced it today to sixty five. That's all right here."),
    (
        SpeakerType.AGENT,
        43000,
        55000,
        "Sixty five dollars for how many MBPS? Do you know the speed? How do you care? Twenty five. Twenty five Mbps? Yeah. Okay. And how many people are using the Internet? Just myself. Are you used to Internet? Are you do gaming, video streaming?",
    ),
    (
        SpeakerType.CUSTOMER,
        56000,
        69000,
        "Work from home? Yeah. I do. No. I don't work from home. I just watch, you know, Netflix and that sort of stuff, and I've seen my, TV still at, like, channel seven channel nine, whatever. Okay. I stream that through the Internet.",
    ),
    (SpeakerType.AGENT, 70000, 74000, "And do you need the home phone line? Do you need a landline or no?"),
    (SpeakerType.CUSTOMER, 74500, 75500, "No."),
    (
        SpeakerType.AGENT,
        76000,
        86000,
        "Okay. Because I just want to tell you, I can give you a twenty five MBBS for, only forty two dollars and ninety Mhmm. For the first six months.",
    ),
    (SpeakerType.CUSTOMER, 87000, 89500, "Yep. And then what does it go up to?"),
    (
        SpeakerType.AGENT,
        90000,
        97000,
        "Seventy two dollars and ninety. That's the regular price. Yeah. See, I'm I'm beyond that. But with that, I",
    ),
    (
        SpeakerType.CUSTOMER,
        97500,
        104000,
        "might save myself twenty dollars a month for six months, butthen it's then I have seven dollars a month here.",
    ),
    (
        SpeakerType.AGENT,
        105000,
        119000,
        "I'm going on. But So you're notno last in contract with the plan. It's just a month to month contract. I mean Yeah. Before the six weeks expire, you can visit again our website and see if we can give you another set of promotion of this, ma'am.",
    ),
    (
        SpeakerType.CUSTOMER,
        120000,
        127000,
        "Yeah. Yeah. Maybe I'll juststay where I am. I couldn't be bothered because I have to paynot much savings.",
    ),
    (
        SpeakerType.AGENT,
        128000,
        136000,
        "I really understand. Again, that's still Okay. Twenty dollars. I can also give you a free modem with thatwith no extra cost.",
    ),
    (SpeakerType.CUSTOMER, 137000, 139000, "Who is that through?"),
    (SpeakerType.AGENT, 140000, 142000, "That is from [PROVIDER_A]."),
    (
        SpeakerType.CUSTOMER,
        143000,
        151000,
        "Right. [PROVIDER_A]. So free modemYep. And forty nine dollars a month for forty two dollars a month. Dollars. Yeah. Do I get a check for it?",
    ),
    (
        SpeakerType.AGENT,
        152000,
        162000,
        "No. All the NBN, all all the NBN plans, they're using only one network, all the retailers. That's the NBN phone. K? But for thethe mobile SIM plan, kindly use it at Telstra network.",
    ),
    (SpeakerType.CUSTOMER, 163000, 166500, "I can. And would it be a new modemor a refurbished one?"),
    (
        SpeakerType.AGENT,
        167000,
        177000,
        "So that's the brand new modembrand new modem. It's all yours. It's hundred percent free. Even you switch provider, even you move to a different property, you can keep and use the same modem.",
    ),
    (
        SpeakerType.CUSTOMER,
        178000,
        189000,
        "No need to repair. Happens if what happens if at the end of six months when it goes up to seventy two dollarsand I change, do I get to get the modemor do I get to the account then? No. No.",
    ),
    (
        SpeakerType.AGENT,
        190000,
        201000,
        "You it's hundred percent free. It's all yours. Even you switch provider, even you move to a different property, you can use and keep it. No need to return it. K? Again, it's hundred percent free.",
    ),
    (SpeakerType.CUSTOMER, 202000, 207000, "Okay. So how does it how does it work? How does how doesget changed over?"),
    # Page 3
    (
        SpeakerType.AGENT,
        208000,
        217000,
        "No. We can quickly set this up for you without paying any status fee. K? NowI just want to tell you that how do I get the modem? Yeah. It will be delivered to you within three to five business days.",
    ),
    (SpeakerType.CUSTOMER, 218000, 221000, "Okay. And is there a cost involved in having it delivered?"),
    (SpeakerType.AGENT, 222000, 225000, "No. It's hundred percent. No extra cost."),
    (SpeakerType.CUSTOMER, 226000, 229000, "Okay. Alright. Yep. Sounds like a good deal."),
    (
        SpeakerType.AGENT,
        230000,
        290000,
        "Yeah. That's why we can quickly set it up for you so you can get the free modem, k, within three to five business days. Now I just want to tell you that again, here are some detail, here here are some more details about it, ma'am. This value plan from [PROVIDER_A] helps with comes with a one to one contract only and, again, provides twenty five Mbps typical in download speed and eight point five Mbps typical in the upload speed from seven PM to eleven PM. Again, the original plan cost is seventy two dollars and ninety per month, but we have an offer ongoing where you will get this plan as forty two dollars and ninety only per month for the first six months and then seventy two dollars and ninety. K? And then, I just want to tell you that the modem that you will receive is the Netcom CF forty Wi Fi six modem. K? Again, it's hundred percent free. No extra cost. It's all yours. K? And then the good thing with the modem, [CUSTOMER_NAME], it's suitable for FTTT, HFC, FTTs, and fixed wireless connection types. That means it's almost compatible to all NBN plans. K? And this is already a Wi Fi six modem. It's already preconfigured. That means it's plugged and free. K? And it's still used in the twenty ten. Okay? So the delivery of the modem into a PowerPointwhen I get it? You just did And it's good to go. K?",
    ),
    (SpeakerType.CUSTOMER, 291000, 295000, "Okay. So there's no setting up or anything like that. You just plug it in? Yep."),
    (
        SpeakerType.AGENT,
        296000,
        316000,
        "Because it's already preconfigured to [PROVIDER_A]. K? That's why you you don't need to reconfigure it. K? Okay. Yep. And then again, the total minimum cost will be forty two dollars and ninety only. No setup fee. No any additional cost. K? Yep. And this will be under your name. Am I correct? Yes. How do you want to address your name, dismissed or missus, or do you have any title?",
    ),
    (SpeakerType.CUSTOMER, 317000, 321000, "Missus [CUSTOMER_NAME]. Yeah. [CUSTOMER_FULL_NAME]."),
    (SpeakerType.AGENT, 322000, 326000, "Yeah. Can you please verify again your first and last name as per ID, please?"),
    (SpeakerType.CUSTOMER, 327000, 329000, "Sorry. I didn't get that."),
    (SpeakerType.AGENT, 330000, 333000, "Can you please verify your first and last name as per ID?"),
    (SpeakerType.CUSTOMER, 334000, 336000, "[CUSTOMER_FULL_NAME]."),
    (SpeakerType.AGENT, 337000, 339000, "[CUSTOMER_NAME] or [CUSTOMER_NAME]?"),
    (SpeakerType.CUSTOMER, 340000, 342000, "Well, I go by [CUSTOMER_NAME]."),
    (
        SpeakerType.AGENT,
        343000,
        358000,
        "[CUSTOMER_NAME]. Okay. [CUSTOMER_NAME]. Yeah. Okay. But, again, [CUSTOMER_NAME]. Right? Because that is the exact bill that you will, you will see on the bill. K? Yep. Mhmm. Missus [CUSTOMER_FULL_NAME]. Right? Yes. Okay. And then your email address, can you please also verify it? It's [EMAIL]. Thank you. And then your mobile number, can you please also verify it?",
    ),
    (SpeakerType.CUSTOMER, 359000, 361000, "[PHONE]."),
    (SpeakerType.AGENT, 362000, 364000, "Okay. And your date of birth?"),
    (SpeakerType.CUSTOMER, 365000, 367000, "[DOB]."),
    (SpeakerType.AGENT, 368000, 372000, "Okay. And then do you want to add a secondary mobile number?"),
    (SpeakerType.CUSTOMER, 373000, 375000, "Sorry. What was that?"),
    (
        SpeakerType.AGENT,
        376000,
        383000,
        "Do you want to add a secondary mobile number or alternate mobile number? No. Okay. And you are currently with I Primus. Right?",
    ),
    (SpeakerType.CUSTOMER, 384000, 386000, "That's correct. Yes."),
    # Page 4
    (SpeakerType.AGENT, 387000, 394000, "Are you able to pull up your I Primus bill or no? Right now? Hang yep. Hang on. Yes, please."),
    (SpeakerType.CUSTOMER, 395000, 398000, "Yep. Got [ACCOUNT_NUMBER]."),
    (SpeakerType.AGENT, 399000, 403000, "Can you please check if you can see the a b c ID? A b c ID."),
    (SpeakerType.CUSTOMER, 404000, 406000, "A b c?"),
    (SpeakerType.AGENT, 407000, 409000, "Yep. A b c I d."),
    (SpeakerType.CUSTOMER, 410000, 414000, "I got issue date. I've seen that balance. Clear button. Customer number? Is that it?"),
    (SpeakerType.AGENT, 415000, 419000, "No. ABC IDs. You can, you can check it, but if it's not visible, it's okay."),
    (SpeakerType.CUSTOMER, 420000, 422500, "I've got Internet service number."),
    (SpeakerType.AGENT, 423000, 426000, "It's okay if you don't see it. That means it's not visible on the bill."),
    (SpeakerType.CUSTOMER, 427000, 431000, "Yeah. No. I I can't see it anywhere there. It's okay. And then again,"),
    (
        SpeakerType.AGENT,
        432000,
        448000,
        "the connection address will be [SERVICE_ADDRESS]. Correct? Yeah. And how how soon do you want your connection to be at the address? As soon as possible, or do you prefer the same? As soon as possible. As soon as possible. Okay. And, do you want your modem to be delivered at the same address, or do you want a different address? Same address? Same address. Yeah. Okay. Again, the delivery will be three to five business days. K?",
    ),
    (
        SpeakerType.CUSTOMER,
        449000,
        462000,
        "Yeah. No. Just mhmm. Just with with the delivery, of the modem, the [STREET_NAME] entrance is closed at the moment. So they will have to come to [DELIVERY_ADDRESS]. There's two entrances. [DELIVERY_ADDRESS].",
    ),
    (SpeakerType.AGENT, 463000, 465000, "I see. Okay."),
    (SpeakerType.CUSTOMER, 466000, 469000, "Yeah. Because I can't get you in the pre code."),
    (
        SpeakerType.AGENT,
        470000,
        479000,
        "I see. Okay. It's already noted. Okay? Now, again, to set up your account, [CUSTOMER_NAME], we need to collect your preferred payment method. Are you using a credit card or debit card?",
    ),
    (SpeakerType.CUSTOMER, 480000, 482000, "And my what, sir?"),
    (
        SpeakerType.AGENT,
        483000,
        493000,
        "I again, to set up your account, we need to collect your preferred payment method because this will be direct debitedevery month from the account from the account. Mhmm.",
    ),
    (SpeakerType.CUSTOMER, 494000, 496000, "Okay."),
    (
        SpeakerType.AGENT,
        497000,
        513000,
        "Are you okay. But before that, I need to mute the recording. K? Okay. The recording is already resumed. Now mhmm. Can you please, do you have access on your email right now? Right?",
    ),
    (SpeakerType.CUSTOMER, 514000, 516000, "Yes. I do."),
    (
        SpeakerType.AGENT,
        517000,
        528000,
        "Okay. I'm not sending in. Okay. Can you please check? I just sent it, I think ten minutes ago, the email. Just let me know if you repeat. It's from Equinix comparison.",
    ),
    (SpeakerType.CUSTOMER, 529000, 531500, "Yep. Yep. Correct. Yep."),
    (SpeakerType.AGENT, 532000, 536000, "Yeah. Open the email and then click view plan."),
    (SpeakerType.CUSTOMER, 537000, 538500, "Yeah."),
    (SpeakerType.AGENT, 539000, 543000, "Okay. After you click view plan, you will see the plan details. Right?"),
    (SpeakerType.CUSTOMER, 544000, 548000, "Yep. So you're in the Yep. Travel there, and travel."),
    (
        SpeakerType.AGENT,
        549000,
        561000,
        "So on the lower part of it, can you please click apply now? Yes. Okay. After you click apply now yep. Click apply now, and it will load, and you will go to the modem. K? Now on the modem, can you please look for the Netcom p s forty Wi Fi six modem?",
    ),
    # Page 5
    (SpeakerType.CUSTOMER, 562000, 566000, "The Wi Fi six pre configured. Is that the one?"),
    (
        SpeakerType.AGENT,
        567000,
        576000,
        "Yeah. The Netcom CF forty Wi Fi six. Right? CF forty Wi Fi six. Yep. Do you see the zero dollar upfront? Right? Yep. Yep. Yep. Yeah. Can you please select it? Make sure that you selected it.",
    ),
    (SpeakerType.CUSTOMER, 577000, 579000, "Yep. I've selected that."),
    (
        SpeakerType.AGENT,
        580000,
        587000,
        "Okay. And then after that, scroll it down. Yep. Now you will see the total minimum cost of three hundred seventeen dollars. Right?",
    ),
    (SpeakerType.CUSTOMER, 588000, 589500, "Yeah."),
    (
        SpeakerType.AGENT,
        590000,
        617000,
        "Yep. You don't have to worry. If you will see the new development fee, right, of two hundred seventy five dollars, You don't have to worry. You will not pay for that because your address is already an NBN ready. That is only applicablefor a newly built house. K? Because they need to install the NBN infrastructure of the address. That's why if you can see, the June development fee, there's aopen and close parenthesisifapplicable. K? But your address is not applicable for that. K? So you just need the payment. And then click next personal detail.",
    ),
    (SpeakerType.CUSTOMER, 618000, 620000, "Yep. Next address details?"),
    (
        SpeakerType.AGENT,
        621000,
        645000,
        "Yeah. Make sure all the information are correct, and then click next address detail. It's still showing that minimum cost of three hundred and seventeen, but don't worry about that. I understand. It's okay. You don't need to worry. Okay? It will not be charged the two hundred seven dollars. And then, next address, you will see the address. Yeah. You will see, next address yep. You will need to, select as soon as possibleon the connection date. Andthenon the delivery of the modem, selectyes. K? I mean, the the the, thethe address of the delivery.",
    ),
    (
        SpeakerType.CUSTOMER,
        646000,
        660000,
        "Okay. So do you want the modem to be delivered at the current address? Click no? Yes. Select yes. No. Select yes. Because it will be the same address. Right? It will be delivered at the same address. No. They've got a delivery to [DELIVERY_ADDRESS].",
    ),
    (
        SpeakerType.AGENT,
        661000,
        667000,
        "I see. Okay. Can you please, select no? Yep. Click no and then select the exact address. K? Yeah.",
    ),
    (SpeakerType.CUSTOMER, 668000, 671000, "[DELIVERY_ADDRESS]. Opt"),
    (SpeakerType.AGENT, 672000, 675000, "Just let me know if you have any additional questions. K?"),
    (
        SpeakerType.CUSTOMER,
        676000,
        686000,
        "It says addressaddress not found. Please enter correct addressor enter it manually. So I've entered it manually. Right. [UNCLEAR_NAME], can you please enter it manually?",
    ),
    (SpeakerType.AGENT, 687000, 688500, "That"),
    (
        SpeakerType.CUSTOMER,
        689000,
        695000,
        "I'm trying to stop not still. I'm trying to k. It's still coming up with that. I'll put my card details in.",
    ),
    (
        SpeakerType.AGENT,
        696000,
        715000,
        "So it's still coming up with that three hundred and seventeen dollars, but don't worry about that. I see. You don't need to worry. I really guarantee you it will not be charged. K? Okay. So You need to only forty forty two dollars. Detail? Yep. Click next review details. Make sure that the, you, tick the boxesthat you agree. Yep.",
    ),
    (SpeakerType.CUSTOMER, 716000, 718000, "Mhmm. Yep."),
    (SpeakerType.AGENT, 719000, 722000, "Nah. Just me. And you will seemhmm."),
    (SpeakerType.CUSTOMER, 723000, 725500, "I'll just try putting it in again."),
    (SpeakerType.AGENT, 726000, 730000, "Again, what is the delivery address? Can you please tell me?"),
    (SpeakerType.CUSTOMER, 731000, 733500, "It's [DELIVERY_ADDRESS]."),
    (
        SpeakerType.AGENT,
        734000,
        749000,
        "Okay. Okay. Can do it. Yeah. It's okay. Can you please select, can you please selectyes. I will be the one who will change the delivery address. K? So you will not be worried. Again, [SERVICE_ADDRESS]. Right? [SERVICE_ADDRESS]? No. No.",
    ),
    # Page 6
    (SpeakerType.CUSTOMER, 750000, 754000, "No. The address for [STREET_NAME] is [SERVICE_ADDRESS]."),
    (SpeakerType.AGENT, 755000, 758000, "Okay. Hang on. That might let me delivery address?"),
    (
        SpeakerType.CUSTOMER,
        759000,
        771000,
        "Hang on. Let me [DELIVERY_ADDRESS]. Yeah. It's because it's a, [RESIDENTIAL_COMPLEX], and there's two entrances. And one entrance the [STREET_NAME] entrance is closed at the moment, so you can't get up that road.",
    ),
    (SpeakerType.AGENT, 772000, 774000, "I see. Because"),
    (SpeakerType.CUSTOMER, 775000, 779000, "It's okay. It's I think it's allowing me to put it inbit by bit."),
    (SpeakerType.AGENT, 780000, 783000, "Okay. [SERVICE_ADDRESS]."),
    (SpeakerType.CUSTOMER, 783500, 785500, "[SERVICE_ADDRESS]"),
    (SpeakerType.AGENT, 786000, 787000, "."),
    (SpeakerType.CUSTOMER, 788000, 792000, "Okay. So a text message, [OTP_CODE]."),
    (
        SpeakerType.AGENT,
        793000,
        800000,
        "Mhmm. And then click submit application. Just let me know if you already have the reference number.",
    ),
    (SpeakerType.CUSTOMER, 801000, 802500, "Yep."),
    (SpeakerType.AGENT, 803000, 805000, "What is the reference number?"),
    (SpeakerType.CUSTOMER, 806000, 809000, "[REFERENCE_NUMBER]."),
    (
        SpeakerType.AGENT,
        810000,
        816000,
        "Thank you for that. That means that you already take advantage of the offer. Okay?",
    ),
    (SpeakerType.CUSTOMER, 817000, 820000, "Yeah. So this is an Ambien. Yeah."),
    (
        SpeakerType.AGENT,
        821000,
        844000,
        "That is an Ambien. K? Yeah. Yeah. Yeah. Okay. Congratulationsfor choosing [PROVIDER_A]. You need to wait for the delivery of the modem. It will be three to five business days. K? And after that, you can activate and connect it. And then now since we already help you with your Internet, how about your electricity and gas? Maybe we could also give you a picture of that. No. I don't have gas, and my electricity",
    ),
    (
        SpeakerType.CUSTOMER,
        845000,
        857000,
        "is all, With aircon? I buy it off the complex that I live in. It doesn't go through I see. So it's embedded. Or anything like that. Yeah.",
    ),
    (
        SpeakerType.AGENT,
        858000,
        869000,
        "I see. Okay. If that's the case here, again, [CUSTOMER_NAME], congratulations for choosing [PROVIDER_A]. Thank you also for choosing Econnex Comparison. Do you have another question?",
    ),
    (SpeakerType.CUSTOMER, 870000, 874000, "No. Do you have acontact phone number I can contact you on if"),
    (
        SpeakerType.AGENT,
        875000,
        887000,
        "I have You will see it, on the, yeah. You will see it on the, you will see the page of the reference number. Right? Below that, you will see all the contact number that you can contact. K?",
    ),
    (SpeakerType.CUSTOMER, 888000, 891000, "Yeah. Okay. Yep."),
    (
        SpeakerType.AGENT,
        892000,
        910000,
        "Yep. This is it? Okay. Thank you. From the lower price. Okay. Yeah. Again, thank you also, [CUSTOMER_NAME]. Okay? Congratulations. This is [AGENT_NAME] again from Equinix Comparison. Again, it was a pleasure to help you out. K? Cheers, and have a wonderful day.",
    ),
    (SpeakerType.CUSTOMER, 911000, 913000, "Okay. Thank you."),
    (SpeakerType.AGENT, 914000, 917000, "You're welcome. Bye for now. Bye."),
]


async def seed_econnex_transcript(database_url: str):
    print(f"Connecting to database at {database_url}...")
    engine = create_async_engine(database_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    now = datetime(2026, 9, 19, 10, 0, 0, tzinfo=UTC)
    total_duration_sec = 920.0

    async with session_factory() as session:
        sale_repo = SqlAlchemySaleRepository(session)
        tr_repo = SqlAlchemyTranscriptRepository(session)
        chk_repo = SqlAlchemyCheckLibraryRepository(session)
        eval_repo = SqlAlchemyEvaluationRepository(session)

        # 1. Retailer: [PROVIDER_A]
        print("Registering Provider and Econnex Campaign...")
        retailer = Retailer(
            id="ret-provider-a",
            code="PROVIDER_A",
            name="[PROVIDER_A] Broadband",
            vertical="TELCO",
        )
        await sale_repo.save_retailer(retailer)

        # 2. Campaign: Outbound Internet Comparator
        campaign = Campaign(
            id="camp-econnex-outbound",
            code="CAMP_ECONNEX_OUTBOUND",
            name="Econnex Comparison - Outbound Internet",
            channel="OUTBOUND",
        )
        await sale_repo.save_campaign(campaign)

        # 3. Agent
        agent = Agent(
            id="agent-econnex-01",
            staff_id="AGT_TELCO_01",
            name="[AGENT_NAME]",
            email="agent@econnex.com.au",
        )
        await sale_repo.save_agent(agent)

        # 4. Lead: [CUSTOMER_FULL_NAME]
        lead = Lead(
            id="lead-econnex-3614001",
            customer_name="[CUSTOMER_FULL_NAME]",
            customer_email="[EMAIL]",
            phone="[PHONE]",
            suburb="[SERVICE_ADDRESS]",
            state="NSW",
            postcode="2000",
            created_at=now,
        )
        await sale_repo.save_lead(lead)

        # 5. Sale
        sale = Sale.create(
            sale_id="sale-econnex-3614001",
            lead_id=lead.id,
            retailer_id="retailer-cimet-01",  # Attach to cimet/prod tenant so it appears in active queue!
            campaign_id=campaign.id,
            agent_id=agent.id,
            sale_date=now,
            product_details={
                "provider": "[PROVIDER_A]",
                "plan_name": "[PROVIDER_A] NBN 25/8.5 Value Plan",
                "speed_download_mbps": 25,
                "speed_upload_mbps": 8.5,
                "promo_price_monthly": 42.90,
                "promo_duration_months": 6,
                "ongoing_price_monthly": 72.90,
                "contract_type": "Month-to-month",
                "modem": "NetComm CF40 Wi-Fi 6 ($0 upfront)",
                "total_minimum_cost_verbal": 42.90,
                "total_minimum_cost_webform": 317.00,
                "previous_provider": "iPrimus",
                "previous_plan_cost": 65.00,
                "reference_number": "[REFERENCE_NUMBER]",
                "otp_verified": "[OTP_CODE]",
            },
        )
        await sale_repo.save_sale(sale)

        # 6. Artifacts & Recording
        print("Registering Recording and Diarized Transcript...")
        tx_data = {
            "source": "De-identified Call Transcript (PDF)",
            "customer": "[CUSTOMER_FULL_NAME]",
            "agent": "[AGENT_NAME]",
            "retailer": "[PROVIDER_A]",
            "turns_count": len(RAW_TRANSCRIPT_PAGES),
        }
        tx_bytes = json.dumps(tx_data).encode("utf-8")
        tx_hash = hashlib.sha256(tx_bytes).hexdigest()

        art_audio = ArtifactModel(
            id="art-audio-econnex-3614001",
            lead_id=lead.id,
            storage_key="recordings/econnex_3614001.wav",
            content_hash=hashlib.sha256(b"MOCK_ECONNEX_AUDIO_WAV").hexdigest(),
            content_type="audio/wav",
            size_bytes=44,
            duration_seconds=total_duration_sec,
            metadata_json={"channels": 1, "sample_rate": 8000},
            created_at=now,
        )
        art_tx = ArtifactModel(
            id="art-tx-econnex-3614001",
            lead_id=lead.id,
            storage_key="transcripts/econnex_3614001.json",
            content_hash=tx_hash,
            content_type="application/json",
            size_bytes=len(tx_bytes),
            metadata_json={"source": "PDF Transcript (De-identified)"},
            created_at=now,
        )
        session.add(art_audio)
        session.add(art_tx)
        await session.flush()

        recording = Recording.create(
            sale_id=sale.id,
            artifact_id=art_audio.id,
            dialler_call_id="CALL_ECONNEX_OUTBOUND_01",
            duration_seconds=total_duration_sec,
            call_date=now,
            recording_id="rec-econnex-3614001",
        )
        await tr_repo.save_recording(recording)

        transcript = Transcript(
            id="tx-econnex-3614001",
            recording_id=recording.id,
            source_artifact_id=art_audio.id,
            output_artifact_id=art_tx.id,
            asr_provider="HUMAN_REDACTED_TRANSCRIPT",
            asr_model="official-disclosure-pdf",
            asr_model_version="1.0",
            diarization_provider="SPEAKER_LABELS",
            diarization_version="1.0",
            language="en-AU",
            created_at=now,
        )

        segments = []
        for idx, (spk, start_ms, end_ms, text) in enumerate(RAW_TRANSCRIPT_PAGES, start=1):
            seg = TranscriptSegment.create(
                transcript_id=transcript.id,
                segment_order=idx,
                speaker=spk,
                start_ms=start_ms,
                end_ms=end_ms,
                text=text,
                segment_id=f"seg-econnex-{idx:03d}",
            )
            segments.append(seg)

        await tr_repo.save_transcript(transcript, segments)

        # 7. Comprehensive Deterministic Evaluation
        print("Generating Deterministic Audit Evaluation and Evidence Lineage...")
        run_id = "run-econnex-3614001"
        prov = AIProvenance(
            provider="deterministic-evaluator",
            model="tcp-broadband-policy-engine",
            model_version="2026.1",
            prompt_version="telco.v1",
            check_version="broadband_cis.v1",
            policy_version="policy.v1",
            pipeline_git_sha="git-sha-econnex",
        )

        run = EvaluationRun(
            id=run_id,
            sale_id=sale.id,
            transcript_id=transcript.id,
            checklist_version_id="chk-telco-v1",
            status=EvaluationRunStatus.SUCCEEDED,
            provenance=prov,
            created_at=now,
            tenant_id=sale.retailer_id,
        )

        # Evaluation Results matching the exact PDF evidence:
        results = [
            # Check 1: Call Recording Disclosure (Page 2, seg 4)
            EvaluationResult(
                id="res-econnex-disc",
                evaluation_run_id=run_id,
                check_id="chk-disclosure",
                check_version_id="chk-disc-v1",
                result=CheckOutcome.PASS,
                confidence=0.98,
                score_numeric=100.0,
                is_critical=True,
                reason_codes=["RECORDING_DISCLOSURE_ACKNOWLEDGED"],
            ),
            # Check 2: NBN Evening Peak Speed Disclosure 25/8.5 Mbps (Page 3, seg 30)
            EvaluationResult(
                id="res-econnex-speed",
                evaluation_run_id=run_id,
                check_id="chk-nbn-speed",
                check_version_id="chk-speed-v1",
                result=CheckOutcome.PASS,
                confidence=0.99,
                score_numeric=100.0,
                is_critical=True,
                reason_codes=["PEAK_HOURS_SPEEDS_DISCLOSED"],
            ),
            # Check 3: Promo & Regular Pricing Disclosure ($42.90 / $72.90) (Page 2, 3)
            EvaluationResult(
                id="res-econnex-pricing",
                evaluation_run_id=run_id,
                check_id="chk-rates",
                check_version_id="chk-rates-v1",
                result=CheckOutcome.PASS,
                confidence=0.95,
                score_numeric=100.0,
                is_critical=True,
                reason_codes=["PRICING_STRUCTURE_DISCLOSED"],
            ),
            # Check 4: Script Consistency / Disfluency ("six weeks" vs 6 months) (Page 2, seg 14)
            EvaluationResult(
                id="res-econnex-disfluency",
                evaluation_run_id=run_id,
                check_id="chk-script-accuracy",
                check_version_id="chk-script-v1",
                result=CheckOutcome.FAIL,
                confidence=0.90,
                score_numeric=65.0,
                is_critical=False,
                reason_codes=["INACCURATE_PROMO_DURATION_STATED"],
            ),
            # Check 5: Total Minimum Cost & Fee Waiver ($317 web form vs $42.90 verbal) (Page 5, seg 57)
            EvaluationResult(
                id="res-econnex-tmc",
                evaluation_run_id=run_id,
                check_id="chk-total-minimum-cost",
                check_version_id="chk-tmc-v1",
                result=CheckOutcome.FAIL,
                confidence=0.95,
                score_numeric=50.0,
                is_critical=True,
                reason_codes=["CONTRACT_FORM_PRICE_DISCREPANCY"],
            ),
            # Check 6: PCI-DSS Payment Card Mute Policy (Page 4, seg 52)
            EvaluationResult(
                id="res-econnex-pci-mute",
                evaluation_run_id=run_id,
                check_id="chk-pci-mute",
                check_version_id="chk-pci-v1",
                result=CheckOutcome.PASS,
                confidence=1.0,
                score_numeric=100.0,
                is_critical=True,
                reason_codes=["CALL_MUTED_BEFORE_CARD_CAPTURE"],
            ),
            # Check 7: Delivery Address Override / Workaround (Page 5, seg 72)
            EvaluationResult(
                id="res-econnex-delivery",
                evaluation_run_id=run_id,
                check_id="chk-delivery-process",
                check_version_id="chk-deliv-v1",
                result=CheckOutcome.FAIL,
                confidence=0.85,
                score_numeric=60.0,
                is_critical=False,
                reason_codes=["MANUAL_ADDRESS_CHANGE_WORKAROUND"],
            ),
            # Check 8: Explicit Informed Consent & OTP Submission (Page 6, seg 80, 82)
            EvaluationResult(
                id="res-econnex-consent",
                evaluation_run_id=run_id,
                check_id="chk-consent",
                check_version_id="chk-consent-v1",
                result=CheckOutcome.PASS,
                confidence=0.99,
                score_numeric=100.0,
                is_critical=True,
                reason_codes=["OTP_AUTHORIZATION_VERIFIED"],
            ),
        ]

        # Grounded Evidence items:
        evidences = [
            # Evidence for Call Recording Disclosure (Page 2)
            Evidence(
                id="ev-econnex-disc",
                evaluation_result_id="res-econnex-disc",
                transcript_segment_id="seg-econnex-004",
                transcript_id=transcript.id,
                speaker="AGENT",
                evidence_type=EvidenceType.SUPPORTING,
                start_ms=12000,
                end_ms=38000,
                expected_value="Mandatory call recording notice for QA/training",
                observed_value="please be advised that this call will be recorded for quality assuranceand, training purposes. K?",
                transcript_excerpt="please be advised that this call will be recorded for quality assuranceand, training purposes. K?",
                ai_explanation="Agent provided mandatory recording disclosure at opening of interaction.",
                comparison_source="TCP_CODE_CLAUSE",
                expected_value_source="COMPLIANCE_POLICY",
                observed_value_source="TRANSCRIPT_AGENT_SPEECH",
            ),
            # Evidence for NBN Speed Disclosure (Page 3)
            Evidence(
                id="ev-econnex-speed",
                evaluation_result_id="res-econnex-speed",
                transcript_segment_id="seg-econnex-030",
                transcript_id=transcript.id,
                speaker="AGENT",
                evidence_type=EvidenceType.SUPPORTING,
                start_ms=230000,
                end_ms=290000,
                expected_value="25 Mbps typical download, 8.5 Mbps typical upload (7-11 PM)",
                observed_value="twenty five Mbps typical in download speed and eight point five Mbps typical in the upload speed from seven PM to eleven PM",
                transcript_excerpt="provides twenty five Mbps typical in download speed and eight point five Mbps typical in the upload speed from seven PM to eleven PM.",
                ai_explanation="Complies with ACCC broadband speed disclosure guidelines and NBN Key Fact Sheet.",
                comparison_source="ACCC_BROADBAND_STANDARDS",
                expected_value_source="PLAN_SPECIFICATION",
                observed_value_source="TRANSCRIPT_AGENT_SPEECH",
            ),
            # Evidence for Disfluency ("six weeks" vs 6 months) (Page 2)
            Evidence(
                id="ev-econnex-disfluency",
                evaluation_result_id="res-econnex-disfluency",
                transcript_segment_id="seg-econnex-014",
                transcript_id=transcript.id,
                speaker="AGENT",
                evidence_type=EvidenceType.CONTRADICTING,
                start_ms=105000,
                end_ms=119000,
                expected_value="Before the six months expire",
                observed_value="Before the six weeks expire",
                transcript_excerpt="Before the six weeks expire, you can visit again our website and see if we can give you another set of promotion of this, ma'am.",
                ai_explanation="Agent mistakenly stated 'six weeks' instead of 'six months' for promotional contract window.",
                comparison_source="CAMPAIGN_RULES",
                expected_value_source="PRODUCT_OFFER",
                observed_value_source="TRANSCRIPT_AGENT_SPEECH",
            ),
            # Evidence for Total Minimum Cost Discrepancy (Page 5)
            Evidence(
                id="ev-econnex-tmc",
                evaluation_result_id="res-econnex-tmc",
                transcript_segment_id="seg-econnex-057",
                transcript_id=transcript.id,
                speaker="AGENT",
                evidence_type=EvidenceType.CONTRADICTING,
                start_ms=580000,
                end_ms=587000,
                expected_value="$42.90 Total Minimum Cost",
                observed_value="$317.00 displayed on webform ($275 New Development Fee)",
                transcript_excerpt="Now you will see the total minimum cost of three hundred seventeen dollars. Right? ... You don't have to worry... I really guarantee you it will not be charged. K? Okay. So You need to only forty forty two dollars.",
                ai_explanation="Online portal displayed $317 contract total. Agent provided verbal override assurance that $275 fee does not apply to FTTP address.",
                comparison_source="TCP_CODE_CIS_DISCLOSURE",
                expected_value_source="VERBAL_AGREEMENT",
                observed_value_source="PORTAL_CONTRACT_CONFIRMATION",
            ),
            # Evidence for PCI-DSS Mute Compliance (Page 4)
            Evidence(
                id="ev-econnex-pci-mute",
                evaluation_result_id="res-econnex-pci-mute",
                transcript_segment_id="seg-econnex-052",
                transcript_id=transcript.id,
                speaker="AGENT",
                evidence_type=EvidenceType.SUPPORTING,
                start_ms=497000,
                end_ms=513000,
                expected_value="Mute recording prior to cardholder payment collection",
                observed_value="before that, I need to mute the recording. K? Okay. The recording is already resumed.",
                transcript_excerpt="before that, I need to mute the recording. K? Okay. The recording is already resumed.",
                ai_explanation="Verified PCI-DSS cardholder data protection protocol: line recording was paused/muted during payment entry.",
                comparison_source="PCI_DSS_REQ_3",
                expected_value_source="SECURITY_MUTE_STANDARD",
                observed_value_source="TRANSCRIPT_AGENT_SPEECH",
            ),
            # Evidence for Delivery Address Workaround (Page 5)
            Evidence(
                id="ev-econnex-deliv",
                evaluation_result_id="res-econnex-deliv",
                transcript_segment_id="seg-econnex-072",
                transcript_id=transcript.id,
                speaker="AGENT",
                evidence_type=EvidenceType.CONTRADICTING,
                start_ms=734000,
                end_ms=749000,
                expected_value="Accurate validated address entered into provisioning portal",
                observed_value="Can you please select yes. I will be the one who will change the delivery address.",
                transcript_excerpt="Can you please select yes. I will be the one who will change the delivery address. K? So you will not be worried.",
                ai_explanation="Agent instructed customer to select service address and promised manual offline correction of delivery address.",
                comparison_source="PROVISIONING_PROCEDURES",
                expected_value_source="ORDER_STANDARD",
                observed_value_source="TRANSCRIPT_AGENT_SPEECH",
            ),
            # Evidence for OTP Explicit Consent (Page 6)
            Evidence(
                id="ev-econnex-consent",
                evaluation_result_id="res-econnex-consent",
                transcript_segment_id="seg-econnex-080",
                transcript_id=transcript.id,
                speaker="CUSTOMER",
                evidence_type=EvidenceType.SUPPORTING,
                start_ms=788000,
                end_ms=792000,
                expected_value="Customer authorizes order via OTP and receives reference number",
                observed_value="Okay. So a text message, [OTP_CODE]. ... What is the reference number? [REFERENCE_NUMBER].",
                transcript_excerpt="Okay. So a text message, [OTP_CODE]. ... What is the reference number? [REFERENCE_NUMBER].",
                ai_explanation="Explicit informed consent completed through SMS OTP validation and digital portal submission.",
                comparison_source="EIC_STANDARD",
                expected_value_source="ORDER_AUTHORIZATION",
                observed_value_source="TRANSCRIPT_CUSTOMER_SPEECH",
            ),
        ]

        # Gate Decision: REVIEW_REQUIRED due to the $317 vs $42.90 portal contract discrepancy!
        gate = GateDecision.create(
            sale_id=sale.id,
            evaluation_run_id=run.id,
            status=GateStatus.REVIEW_REQUIRED,
            policy_version="policy.v1",
            decision_reason_code="PORTAL_TOTAL_MINIMUM_COST_MISMATCH",
            decision_id="gate-econnex-3614001",
            warnings=[
                "Online contract displayed $317.00 Total Minimum Cost including unconfirmed $275 New Development Fee; agent verbally guaranteed $42.90.",
                "Agent advised customer to submit incorrect delivery address and promised offline manual modification.",
                "Agent verbally misquoted promo window as 'six weeks' before correcting to 6 months.",
            ],
        )

        await eval_repo.save_evaluation_run(run, results, evidences)
        await eval_repo.save_gate_decision(gate)
        await session.commit()

    await engine.dispose()
    print("Successfully seeded official Redacted Call Transcript into SalesCall QA platform!")


if __name__ == "__main__":
    db_url = "sqlite+aiosqlite:///salescall_qa_seed.db"
    asyncio.run(seed_econnex_transcript(db_url))
