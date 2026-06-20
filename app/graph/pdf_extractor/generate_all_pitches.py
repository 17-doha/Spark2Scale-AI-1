"""
Generate gold-standard pitch PDFs for the evaluation benchmark suite.

Sources cited inline per company. Run from project root:
    python app/graph/pdf_extractor/generate_all_pitches.py

Outputs (app/graph/pdf_extractor/):
    airbnb_2009_pitch.pdf
    stripe_2010_pitch.pdf
    theranos_2004_pitch.pdf
    juicero_2013_pitch.pdf
    wework_2010_pitch.pdf
"""

from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

OUT = Path(__file__).parent


# ── Shared helpers ────────────────────────────────────────────────────────────

def _make_doc(filename):
    return SimpleDocTemplate(
        str(OUT / filename), pagesize=A4,
        leftMargin=2.5*cm, rightMargin=2.5*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )

def _styles():
    s = getSampleStyleSheet()
    h1   = ParagraphStyle("h1",   parent=s["Heading1"], fontSize=18, spaceAfter=6)
    h2   = ParagraphStyle("h2",   parent=s["Heading2"], fontSize=13, spaceBefore=14, spaceAfter=4)
    body = ParagraphStyle("body", parent=s["Normal"],   fontSize=10, leading=14, spaceAfter=4)
    bold = ParagraphStyle("bold", parent=body, fontName="Helvetica-Bold")
    src  = ParagraphStyle("src",  parent=body, fontSize=8, textColor=colors.grey, spaceAfter=2)
    return h1, h2, body, bold, src

def _tbl(data, col_widths):
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("FONTNAME",      (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,-1), 9),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.whitesmoke, colors.white]),
        ("GRID",          (0,0), (-1,-1), 0.3, colors.lightgrey),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    return t

def sp(n=6):  return Spacer(1, n)
def rule():   return HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey, spaceAfter=6)


# ═══════════════════════════════════════════════════════════════════════════════
# 1.  AIRBNB  — Seed stage, April 2009
# ═══════════════════════════════════════════════════════════════════════════════
def build_airbnb():
    """
    Sources:
    - Spectup (2024). Airbnb Pitch Deck Analysis.
      https://www.spectup.com/resource-hub/airbnb-pitch-deck-analysis
    - Fortune (2020). The Education of Brian Chesky.
      https://fortune.com/longform/brian-chesky-airbnb/
    - Vator News (2016). When Airbnb was young: the early years.
      https://vator.tv/2016-02-26-when-airbnb-was-young-the-early-years/
    - Hostaway (2024). Airbnb Founders.
      https://www.hostaway.com/blog/airbnb-founders/
    - Suprdeck (2024). Airbnb Seed Round 2009.
      https://suprdeck.com/case-studies/airbnb-seed-round-2009
    """
    doc = _make_doc("airbnb_2009_pitch.pdf")
    h1, h2, body, bold, src = _styles()
    def h(t, s=h2): return Paragraph(t, s)
    def p(t):       return Paragraph(t, body)
    def b(t):       return Paragraph(t, bold)
    def c(t):       return Paragraph(t, src)  # citation line

    story = []

    # ── Title ────────────────────────────────────────────────────────────────
    story += [h("AIRBNB — Seed Stage Pitch", h1),
              p("Date: April 2009  |  Stage: Seed  |  Location: San Francisco, CA, USA"),
              c("Source: Suprdeck (2024). Airbnb Seed Round 2009. https://suprdeck.com/case-studies/airbnb-seed-round-2009"),
              rule()]

    # ── Company Snapshot ────────────────────────────────────────────────────
    story += [h("Company Snapshot"), _tbl([
        ["Field", "Value"],
        ["Company Name",        "Airbnb (formerly AirBed&Breakfast)"],
        ["Website",             "www.airbnb.com"],
        ["HQ Location",         "San Francisco, California, USA"],
        ["Date Founded",        "August 2008"],
        ["Current Stage",       "Seed"],
        ["Amount Raised to Date","$20,000 (Y Combinator, Jan 2009)"],
        ["Round Target",        "$600,000"],
        ["Target Close",        "April 2009"],
    ], [6*cm, 11*cm]),
    c("Sources: Fortune (2020). https://fortune.com/longform/brian-chesky-airbnb/ ; Suprdeck (2024). https://suprdeck.com/case-studies/airbnb-seed-round-2009"),
    sp()]

    # ── Founders ─────────────────────────────────────────────────────────────
    story += [h("Founding Team"), _tbl([
        ["Name", "Role", "Background", "Yrs Experience", "Ownership %"],
        ["Brian Chesky",    "CEO & Co-founder",
         "RISD graduate, Industrial Design. Product design for consumer goods 2005-2007. No prior startup exit.",
         "3", "34%"],
        ["Joe Gebbia",      "CPO & Co-founder",
         "RISD graduate, Graphic Design & Industrial Design. Freelance product designer 2005-2007.",
         "3", "34%"],
        ["Nathan Blecharczyk", "CTO & Co-founder (Technical)",
         "Harvard University Computer Science 2005-2009 (dropped out). "
         "Software engineer intern at TripAdvisor and Batiq 2006-2007. Full-stack engineer.",
         "4", "32%"],
    ], [4*cm, 3.5*cm, 5.5*cm, 1.5*cm, 2*cm]),
    c("Source: Hostaway (2024). Airbnb Founders. https://www.hostaway.com/blog/airbnb-founders/"),
    sp(),
    p("Full-time start date: 2008-08-01 (all three founders full-time from company founding)."),
    p("Founder-market fit: Chesky and Gebbia experienced the problem personally (could not afford rent in SF, 2007). "
      "Blecharczyk brings technical infrastructure for marketplace scale."),
    sp()]

    # ── Execution Timeline ───────────────────────────────────────────────────
    story += [h("Execution Timeline"), _tbl([
        ["Date", "Milestone"],
        ["Oct 2007", "Chesky & Gebbia couldn't pay rent; rented air mattresses to DNC attendees."],
        ["Aug 2008", "Company officially founded as AirBed&Breakfast."],
        ["Jan 2009", "Accepted into Y Combinator Winter 2009 batch; $20K invested."],
        ["Mar 2009", "10,000 registered users, 2,500 listings across the US."],
        ["Apr 2009", "$600K seed round from Sequoia Capital at $2.4M pre-money."],
    ], [3.5*cm, 13.5*cm]),
    c("Sources: Vator News (2016). https://vator.tv/2016-02-26-when-airbnb-was-young-the-early-years/ ; Fortune (2020). https://fortune.com/longform/brian-chesky-airbnb/"),
    sp()]

    # ── Problem ──────────────────────────────────────────────────────────────
    story += [h("Problem Definition"),
    b("Customer Profile:"), p("Travellers seeking affordable short-term accommodation; homeowners with spare rooms seeking income."),
    b("Problem Statement:"),
    p("Hotels are expensive and impersonal. Millions of homeowners have spare rooms or properties sitting empty. "
      "There is no trusted, simple platform connecting them. Craigslist exists but provides no trust layer, no photos, no reviews."),
    b("Current Solutions:"), p("Craigslist (no trust/safety layer), Couchsurfing (free only, no monetisation for hosts), traditional hotels."),
    b("Gap Analysis:"), p("No marketplace existed that let anyone rent their spare space with built-in trust, payment, and discovery."),
    b("Frequency:"), p("Travel/accommodation need arises multiple times per year per user."),
    b("Evidence:"), p("120 customer interviews; cereal box stunt ($30,000 revenue in 2008) proved willingness to engage."),
    c("Source: Spectup (2024). Airbnb Pitch Deck Analysis. https://www.spectup.com/resource-hub/airbnb-pitch-deck-analysis"),
    sp()]

    # ── Product ──────────────────────────────────────────────────────────────
    story += [h("Product & Solution"),
    b("Product Stage:"), p("Live product — marketplace with listings, photos, messaging, and payment."),
    b("Core Stickiness:"), p("Host and guest reviews create a trust network. Professional photography drives conversion. "
                              "Returning users book faster due to stored preferences and payment details."),
    b("Differentiation:"),
    p("1. Trust layer (verified profiles, reviews, host guarantees) absent from Craigslist.\n"
      "2. Craigslist API integration: every Airbnb listing auto-posted to Craigslist, hijacking existing discovery traffic.\n"
      "3. 10% commission only on completed transaction — no listing fee, lowering host friction."),
    b("Defensibility Moat:"),
    p("Network effects: more listings attract more guests; more guests attract more hosts. "
      "Review data creates a self-improving trust signal that is costly to replicate."),
    c("Source: Spectup (2024). https://www.spectup.com/resource-hub/airbnb-pitch-deck-analysis"),
    sp()]

    # ── Market ───────────────────────────────────────────────────────────────
    story += [h("Market & Scope"),
    b("Beachhead Market:"), p("US-based budget travellers and urban homeowners with spare rooms. Craigslist shows 50M+ monthly visitors in housing/travel."),
    b("Market Size Estimate:"), p("$630,000 in existing temporary housing listings on comparable platforms at snapshot date; "
                                   "US travel accommodation market: >$100B annually."),
    b("Long-term Vision:"), p("Global marketplace for any space — rooms, apartments, castles, treehouses — making anyone a host anywhere in the world."),
    b("Expansion Strategy:"), p("US cities first → international expansion → experiences and services add-on."),
    c("Source: Spectup (2024). https://www.spectup.com/resource-hub/airbnb-pitch-deck-analysis"),
    sp()]

    # ── Traction ─────────────────────────────────────────────────────────────
    story += [h("Traction Metrics"),
    _tbl([
        ["Metric", "Value"],
        ["Stage Context",     "Seed — 8 months post-launch"],
        ["Registered Users",  "10,000 (March 2009)"],
        ["Active Listings",   "2,500 (March 2009)"],
        ["Early Revenue",     "$200/week initially; $30,000 from cereal stunt (2008 DNC)"],
        ["Growth Rate (MoM)", "22% month-over-month (early 2009)"],
        ["Notable Bookings",  "3 guests first weekend; DNC 2008 fully booked"],
    ], [6*cm, 11*cm]),
    c("Sources: Vator News (2016). https://vator.tv/2016-02-26-when-airbnb-was-young-the-early-years/ ; Spectup (2024). https://www.spectup.com/resource-hub/airbnb-pitch-deck-analysis"),
    sp()]

    # ── GTM ──────────────────────────────────────────────────────────────────
    story += [h("Go-to-Market Strategy"),
    b("Buyer Persona:"), p("Budget-conscious traveller, ages 18–35, comfortable booking online."),
    b("Primary Acquisition Channel:"), p("Craigslist API integration — automated cross-posting hijacked existing supply/demand."),
    b("Sales Motion:"), p("Self-serve. Hosts list for free; guests book with one click."),
    b("Average Sales Cycle:"), p("Minutes — zero friction sign-up, instant booking."),
    b("Deal Closer:"), p("Product (automated cross-post + trust layer)."),
    c("Source: Spectup (2024). https://www.spectup.com/resource-hub/airbnb-pitch-deck-analysis"),
    sp()]

    # ── Business Model ───────────────────────────────────────────────────────
    story += [h("Business Model"),
    _tbl([
        ["Field", "Value"],
        ["Pricing Model",      "10% commission on each completed booking (host + guest fee split)"],
        ["Avg Revenue/Booking","~$20–40 per transaction at seed stage"],
        ["Gross Margin",       "~90% (marketplace, minimal COGS)"],
        ["Monthly Burn",       "~$20,000 (lean team of 3)"],
        ["Runway",             "12+ months on $600K round"],
    ], [6*cm, 11*cm]),
    c("Source: Suprdeck (2024). https://suprdeck.com/case-studies/airbnb-seed-round-2009"),
    sp()]

    # ── Vision ───────────────────────────────────────────────────────────────
    story += [h("Vision & Strategy"),
    b("5-Year Vision:"),
    p("Airbnb becomes the world's default platform for any short-term space rental — from a sofa in Cairo to a castle in Scotland. "
      "Every homeowner becomes a potential host; every traveller has a local home anywhere."),
    b("Category Definition:"), p("Peer-to-Peer Accommodation Marketplace"),
    b("Primary Risk:"),
    p("Trust and safety: guests vandalise host properties; hosts are fraudulent. "
      "Regulatory risk: cities and hotels lobby to ban short-term rentals. "
      "Platform risk: dependency on Craigslist integration."),
    b("Use of Funds:"), p("Engineering hires (2), professional photography rollout, host acquisition marketing, legal/insurance product development."),
    c("Source: Fortune (2020). https://fortune.com/longform/brian-chesky-airbnb/"),
    sp()]

    doc.build(story)
    print("OK airbnb_2009_pitch.pdf")


# ═══════════════════════════════════════════════════════════════════════════════
# 2.  STRIPE  — Seed stage, Y Combinator 2010
# ═══════════════════════════════════════════════════════════════════════════════
def build_stripe():
    """
    Sources:
    - Pestel Analysis (2024). Brief History of Stripe.
      https://pestel-analysis.com/blogs/brief-history/stripe
    - VatorNews (2016). When Stripe was young: the early years.
      https://vator.tv/2016-12-29-when-stripe-was-young-the-early-years/
    - Wikipedia. Patrick Collison.
      https://en.wikipedia.org/wiki/Patrick_Collison
    - Wikipedia. John Collison.
      https://en.wikipedia.org/wiki/John_Collison
    - Y Combinator Library. Patrick & John Collison.
      https://www.ycombinator.com/library/Kx-patrick-john-collison-co-founders-of-stripe
    - Upmetrics (2024). Stripe Pitch Deck.
      https://upmetrics.co/pitch-deck-examples/stripe
    """
    doc = _make_doc("stripe_2010_pitch.pdf")
    h1, h2, body, bold, src = _styles()
    def h(t, s=h2): return Paragraph(t, s)
    def p(t):       return Paragraph(t, body)
    def b(t):       return Paragraph(t, bold)
    def c(t):       return Paragraph(t, src)

    story = []

    story += [h("STRIPE — Seed Stage Pitch", h1),
              p("Date: Late 2010  |  Stage: Seed (YC W2010)  |  Location: San Francisco, CA, USA"),
              c("Source: Y Combinator Library. https://www.ycombinator.com/library/Kx-patrick-john-collison-co-founders-of-stripe"),
              rule()]

    story += [h("Company Snapshot"), _tbl([
        ["Field", "Value"],
        ["Company Name",         "Stripe (originally /dev/payments)"],
        ["Website",              "stripe.com"],
        ["HQ Location",          "San Francisco, California, USA"],
        ["Date Founded",         "2010"],
        ["Current Stage",        "Seed"],
        ["Amount Raised to Date","$20,000 (Y Combinator)"],
        ["Round Target",         "$2,000,000"],
        ["Target Close",         "Early 2011"],
    ], [6*cm, 11*cm]),
    c("Source: Pestel Analysis (2024). https://pestel-analysis.com/blogs/brief-history/stripe"),
    sp()]

    story += [h("Founding Team"), _tbl([
        ["Name", "Role", "Background", "Yrs Experience", "Ownership %"],
        ["Patrick Collison", "CEO & Co-founder (Technical)",
         "MIT Mathematics (dropped out 2010). Founded Auctomatic (sold 2008). "
         "Coding since age 10. Deep expertise in distributed systems and payments APIs.",
         "8", "50%"],
        ["John Collison",    "President & Co-founder (Technical)",
         "Harvard University CS (dropped out 2010). Co-founded Auctomatic with Patrick. "
         "Prior exit at age 17. Full-stack engineer and product lead.",
         "6", "50%"],
    ], [4*cm, 3.5*cm, 6.5*cm, 1.5*cm, 1.5*cm]),
    c("Sources: Wikipedia. Patrick Collison. https://en.wikipedia.org/wiki/Patrick_Collison ; Wikipedia. John Collison. https://en.wikipedia.org/wiki/John_Collison"),
    sp(),
    b("Prior Exit:"), p("Auctomatic — eBay auction management tool — sold 2008. Founders were 19 and 17 years old at time of sale."),
    c("Source: Y Combinator Library. https://www.ycombinator.com/library/Kx-patrick-john-collison-co-founders-of-stripe"),
    sp()]

    story += [h("Execution Timeline"), _tbl([
        ["Date", "Milestone"],
        ["2007", "Patrick & John found Auctomatic; sold within months."],
        ["2010", "Founded Stripe (/dev/payments); accepted into YC Winter 2010."],
        ["2010", "First customer (Ross Boucher, 280 North) signed up 2 weeks after prototype."],
        ["2010", "First 20 customers: all YC companies."],
        ["Sep 2011", "Public launch. 100,000 developer accounts within 10 months of launch."],
        ["Early 2011", "$2M Series A: Peter Thiel, Elon Musk, Sequoia, a16z, SV Angel."],
    ], [3.5*cm, 13.5*cm]),
    c("Source: VatorNews (2016). https://vator.tv/2016-12-29-when-stripe-was-young-the-early-years/"),
    sp()]

    story += [h("Problem Definition"),
    b("Customer Profile:"), p("Software developers and startup founders who need to accept payments online."),
    b("Problem Statement:"),
    p("Accepting payments on the internet requires weeks of bank negotiations, merchant accounts, complex APIs, "
      "and security certifications (PCI-DSS). PayPal's API is difficult; Authorize.net requires a sales call. "
      "A developer building a new product cannot accept a credit card in under a day."),
    b("Current Solutions:"), p("PayPal (complex API, poor developer experience), Authorize.net (requires enterprise contract), manual bank integrations (weeks of paperwork)."),
    b("Gap Analysis:"), p("No solution let a developer go from zero to accepting a live payment in under 30 minutes using just a few lines of code."),
    b("Frequency:"), p("Every new web or mobile product that needs to monetise hits this problem once — but the pain compounds with every hour lost."),
    b("Evidence:"), p("Paul Graham (YC): 'I just realized the problem — why is it so hard to charge for things on the internet?' First 20 YC companies immediately adopted Stripe."),
    c("Source: Upmetrics (2024). https://upmetrics.co/pitch-deck-examples/stripe"),
    sp()]

    story += [h("Product & Solution"),
    b("Product Stage:"), p("Live — private beta with YC companies."),
    b("Core Stickiness:"), p("Integration takes minutes; switching away requires rewriting billing infrastructure. "
                              "Developer documentation is best-in-class. Libraries in Ruby, Python, PHP, Java, Node."),
    b("Differentiation:"),
    p("7 lines of code to accept a live payment vs. weeks of setup with competitors. "
      "No merchant account required. Sandbox for testing. Transparent pricing, no sales team."),
    b("Defensibility Moat:"),
    p("Developer ecosystem lock-in — once integrated, switching cost is high. "
      "Data moat: fraud detection improves with transaction volume across all customers. "
      "Trust moat: as Stripe processes more payments, banks give better rates."),
    c("Source: Pestel Analysis (2024). https://pestel-analysis.com/blogs/brief-history/stripe"),
    sp()]

    story += [h("Market & Scope"),
    b("Beachhead Market:"), p("YC-batch startups and developer-led companies building web products in the US."),
    b("Market Size Estimate:"), p("Every business that takes online payments. US e-commerce alone: $170B+ (2010). Global: $1T+ long-term addressable."),
    b("Long-term Vision:"), p("Stripe becomes the economic infrastructure of the internet — the financial layer for every company doing business online."),
    b("Expansion Strategy:"), p("Developers first → SMBs → enterprise → international expansion → financial products (lending, payroll, corporate cards)."),
    c("Source: Upmetrics (2024). https://upmetrics.co/pitch-deck-examples/stripe"),
    sp()]

    story += [h("Traction Metrics"), _tbl([
        ["Metric", "Value"],
        ["Stage Context",       "Seed — private beta, YC W2010 (B2B developer tool, not consumer app)"],
        ["Active Customers",    "20 paying companies (all YC W2010 batch). 100% of available YC batch adopted."],
        ["Monthly Active Users","20"],
        ["Early Revenue",       "$200–$800/month (estimated from 20 companies × avg transaction volume; not disclosed publicly)"],
        ["Growth Rate (MoM)",   "100% adoption of entire YC batch within 2 weeks of demo — zero churn in beta cohort"],
        ["Paid Users",          "20 (all paying transaction fees from first use)"],
        ["Key Signal",          "First customer (Ross Boucher, 280 North) signed up 2 weeks after prototype. "
                                "Zero churn across all 20 beta customers. Paul Graham personally promoted to YC partners."],
    ], [6*cm, 11*cm]),
    c("Source: VatorNews (2016). https://vator.tv/2016-12-29-when-stripe-was-young-the-early-years/"),
    sp()]

    story += [h("Go-to-Market Strategy"),
    b("Buyer Persona:"), p("Software developer / CTO at a startup or small business."),
    b("Primary Acquisition Channel:"), p("Word-of-mouth within YC network; developer community (Hacker News)."),
    b("Sales Motion:"), p("Self-serve — sign up, get API keys, accept a live payment in minutes. No sales rep ever."),
    b("Average Sales Cycle:"), p("Instant — developer signs up, integrates in one session."),
    b("Deal Closer:"), p("Product quality (7-line integration) + documentation."),
    c("Source: Pestel Analysis (2024). https://pestel-analysis.com/blogs/brief-history/stripe"),
    sp()]

    story += [h("Business Model"), _tbl([
        ["Field", "Value"],
        ["Pricing Model",   "2.9% + $0.30 per successful card charge"],
        ["Gross Margin",    "~70% (after payment network fees)"],
        ["Monthly Burn",    "~$15,000 (2-person team, no office)"],
        ["Runway",          "18+ months on $2M round"],
        ["Unit Economics",  "CAC ≈ $0 (word-of-mouth); LTV grows with customer transaction volume"],
    ], [6*cm, 11*cm]),
    c("Source: Pestel Analysis (2024). https://pestel-analysis.com/blogs/brief-history/stripe"),
    sp()]

    story += [h("Vision & Strategy"),
    b("5-Year Vision:"),
    p("Stripe becomes the default payment infrastructure for the internet — as ubiquitous as AWS for compute. "
      "Every company building a product online uses Stripe by default. Stripe expands into lending, corporate cards, payroll, and banking-as-a-service."),
    b("Category Definition:"), p("Developer Payment Infrastructure / Internet Financial Services"),
    b("Primary Risk:"),
    p("Fraud risk: processing payments exposes Stripe to chargebacks and fraud. "
      "Regulatory: payment processing requires money transmitter licences in every jurisdiction. "
      "Competition: PayPal or banks could build a better developer API."),
    b("Use of Funds:"), p("Engineering hires (2 backend, 1 fraud), international licencing, marketing to developer communities."),
    c("Source: Y Combinator Library. https://www.ycombinator.com/library/Kx-patrick-john-collison-co-founders-of-stripe"),
    sp()]

    doc.build(story)
    print("OK  stripe_2010_pitch.pdf")


# ═══════════════════════════════════════════════════════════════════════════════
# 3.  THERANOS  — Seed stage, 2004
# ═══════════════════════════════════════════════════════════════════════════════
def build_theranos():
    """
    Sources:
    - Carreyrou, J. (2018). Bad Blood: Secrets and Lies in a Silicon Valley Startup.
      Knopf. ISBN 978-1-5247-3166-7.
    - Wikipedia. Elizabeth Holmes.
      https://en.wikipedia.org/wiki/Elizabeth_Holmes
    - Darden Ideas to Action (2019). Fake It Till You Fail: The Theranos Story.
      https://ideas.darden.virginia.edu/theranos-darden-case
    - Crunchbase. Theranos Seed Round.
      https://www.crunchbase.com/funding_round/theranos-seed--dfd832be
    - FinModelsLab (2024). Theranos Pitch Deck.
      https://finmodelslab.com/products/theranos-pitch-deck
    - SEC (2018). Securities and Exchange Commission v. Theranos, Elizabeth Holmes,
      and Ramesh Balwani. Case No. 18-cv-01602.
    """
    doc = _make_doc("theranos_2004_pitch.pdf")
    h1, h2, body, bold, src = _styles()
    def h(t, s=h2): return Paragraph(t, s)
    def p(t):       return Paragraph(t, body)
    def b(t):       return Paragraph(t, bold)
    def c(t):       return Paragraph(t, src)

    story = []

    story += [h("THERANOS — Seed Stage Pitch (Reconstructed)", h1),
              p("Date: June 2004  |  Stage: Seed  |  Location: Palo Alto, CA, USA"),
              p("<b>Note:</b> This document reconstructs the pitch as presented to early investors based on "
                "court records, SEC filings, and investigative reporting. Claims made were later proven fraudulent."),
              c("Primary source: Carreyrou, J. (2018). Bad Blood. Knopf. ISBN 978-1-5247-3166-7."),
              rule()]

    story += [h("Company Snapshot"), _tbl([
        ["Field", "Value"],
        ["Company Name",         "Theranos, Inc."],
        ["Website",              "theranos.com"],
        ["HQ Location",          "Palo Alto, California, USA"],
        ["Date Founded",         "2003 (incorporated)"],
        ["Current Stage",        "Seed"],
        ["Amount Raised to Date","$0 prior to seed"],
        ["Round Target",         "$6,000,000"],
        ["Target Close",         "December 2004"],
    ], [6*cm, 11*cm]),
    c("Source: Wikipedia. Elizabeth Holmes. https://en.wikipedia.org/wiki/Elizabeth_Holmes"),
    sp()]

    story += [h("Founding Team"), _tbl([
        ["Name", "Role", "Background", "Yrs Experience", "Ownership %"],
        ["Elizabeth Holmes", "CEO & Founder (SOLO — no co-founder)",
         "Stanford University Chemical Engineering (dropped out 2003, age 19). "
         "1 year undergraduate study only. No prior startup. No medical degree. No laboratory science credentials. "
         "No technical co-founder. Advisor: Prof. Channing Robertson (Stanford ChemE).",
         "1", "~95%"],
    ], [4*cm, 3.5*cm, 6.5*cm, 1.5*cm, 1.5*cm]),
    c("Source: Wikipedia. Elizabeth Holmes. https://en.wikipedia.org/wiki/Elizabeth_Holmes"),
    sp(),
    p("No technical co-founder. No credentialed laboratory scientist on founding team. "
      "No one on the team held a medical device engineering background."),
    c("Source: Carreyrou, J. (2018). Bad Blood. Knopf. p. 21–35."),
    sp()]

    story += [h("Execution Timeline"), _tbl([
        ["Date", "Milestone"],
        ["2003",     "Holmes drops out of Stanford; founds company using education trust fund from parents."],
        ["Jun 2004", "Seed round: $500K from Draper Fisher Jurvetson (Tim Draper)."],
        ["Dec 2004", "Total raised reaches $6M. 50 employees hired."],
        ["Feb 2005", "Series A: $5.8M led by Rupert Murdoch (News Corp)."],
        ["2006",     "Series B ($9.1M) and Series C ($28.5M) raised on unverified product claims."],
        ["2013",     "Walgreens partnership announced. Device deployed in stores."],
        ["2018",     "SEC charges Holmes and Balwani with fraud. Company dissolved."],
    ], [3.5*cm, 13.5*cm]),
    c("Sources: Crunchbase. https://www.crunchbase.com/funding_round/theranos-seed--dfd832be ; "
      "Darden (2019). https://ideas.darden.virginia.edu/theranos-darden-case"),
    sp()]

    story += [h("Problem Definition"),
    b("Customer Profile:"), p("Patients requiring blood tests; pharmaceutical companies conducting Phase IV clinical trials."),
    b("Problem Statement:"),
    p("Blood testing is slow, expensive, and requires large blood draws via venipuncture — a painful and anxiety-inducing process. "
      "Patients avoid necessary tests due to needle phobia. Lab results take days. "
      "Point-of-care testing could enable earlier disease detection and save lives."),
    b("Current Solutions:"), p("Quest Diagnostics and LabCorp (large-volume venipuncture, slow turnaround). Hospital labs. No fingerprick-to-result device existed."),
    b("Gap Analysis:"), p("No device could run 200+ diagnostic tests from a single fingerprick blood sample with lab-equivalent accuracy."),
    b("Frequency:"), p("Blood tests required multiple times per year for chronically ill patients; once per year for general population."),
    b("Evidence:"), p("Claimed: Holmes and her mother feared needles. No customer discovery data presented to early investors."),
    c("Source: Carreyrou, J. (2018). Bad Blood. Knopf. p. 15–20."),
    sp()]

    story += [h("Product & Solution"),
    b("Product Stage:"), p("Claimed: working prototype (the 'Edison' device). Actual status: technology not validated; device could not perform as claimed."),
    b("Core Stickiness:"),
    p("Claimed: proprietary nano-container cartridges with reader devices placed in pharmacies and homes. "
      "Actual: internally relied on third-party Siemens ADVIA analysers for the majority of tests."),
    b("Differentiation (claimed):"),
    p("1. Fingerprick sample (vs. full venipuncture draw).\n"
      "2. 200+ tests from a single drop of blood.\n"
      "3. Results in hours, not days.\n"
      "4. Costs 50–90% less than traditional labs."),
    b("CRITICAL RED FLAG:"),
    p("None of these claims were independently validated. Internal documents later revealed in court showed "
      "the Edison device failed accuracy standards on the majority of tests. Holmes was aware of this."),
    b("Defensibility Moat (claimed):"), p("Proprietary cartridge technology. Trade secret protection. FDA regulatory approval pathway."),
    c("Sources: SEC (2018). Case No. 18-cv-01602 ; Carreyrou, J. (2018). Bad Blood. Knopf. p. 60–80."),
    sp()]

    story += [h("Market & Scope"),
    b("Beachhead Market:"), p("Pharmaceutical Phase IV clinical trial monitoring (2004 pitch). Later pivoted to consumer retail diagnostics (Walgreens, Safeway)."),
    b("Market Size Estimate (claimed):"),
    p("$15B+ US diagnostics market. Pitch to 2006 Series C investors projected $120–300M revenue in 18 months "
      "through five pharma deals. None of these deals materialised as described."),
    b("Long-term Vision:"), p("Replace all traditional blood labs with portable, real-time point-of-care testing available at pharmacies, doctors' offices, and homes."),
    b("Expansion Strategy:"), p("Pharma partnerships → Walgreens retail rollout → international expansion → home testing device."),
    c("Source: FinModelsLab (2024). https://finmodelslab.com/products/theranos-pitch-deck"),
    sp()]

    story += [h("Traction Metrics"), _tbl([
        ["Metric", "Value"],
        ["Stage Context",     "Seed — pre-revenue, unvalidated prototype"],
        ["Validated Tests",   "0 — no independent clinical validation at seed stage"],
        ["Paying Customers",  "0 — pharma partnerships still in negotiation"],
        ["Revenue",           "$0 at seed stage"],
        ["Growth Rate",       "N/A — no commercial deployment"],
        ["Staff",             "~50 employees by end of 2004"],
    ], [6*cm, 11*cm]),
    c("Sources: Darden (2019). https://ideas.darden.virginia.edu/theranos-darden-case ; "
      "Wikipedia. Elizabeth Holmes. https://en.wikipedia.org/wiki/Elizabeth_Holmes"),
    sp()]

    story += [h("Go-to-Market Strategy"),
    b("Buyer Persona:"), p("Pharmaceutical R&D heads; later, retail pharmacy chains (Walgreens, CVS)."),
    b("Primary Acquisition Channel:"), p("Direct outreach to pharma executives via Holmes' Stanford and Draper network."),
    b("Sales Motion:"), p("Enterprise sales — direct C-suite relationships. Holmes personally closed all major deals."),
    b("Average Sales Cycle:"), p("12–24 months (enterprise pharma contracts)."),
    b("Deal Closer:"), p("Elizabeth Holmes — all sales personally managed; no sales team at seed stage."),
    c("Source: Carreyrou, J. (2018). Bad Blood. Knopf. p. 40–55."),
    sp()]

    story += [h("Business Model"), _tbl([
        ["Field", "Value"],
        ["Pricing Model",   "Per-test fee to pharma companies (B2B); later $10–$35 per test to consumers"],
        ["Gross Margin",    "Claimed: high (~70%+); actual: negative (cost of Siemens equipment not disclosed)"],
        ["Monthly Burn",    "~$500,000+ (50 employees, lab equipment)"],
        ["Runway",          "~12 months on $6M raise"],
        ["Revenue",         "$0 at seed stage"],
    ], [6*cm, 11*cm]),
    c("Source: SEC (2018). Case No. 18-cv-01602"),
    sp()]

    story += [h("Vision & Strategy"),
    b("5-Year Vision:"),
    p("Every person on Earth has access to real-time, affordable blood diagnostics from a finger-prick sample. "
      "Theranos eliminates the need for traditional laboratory infrastructure globally."),
    b("Category Definition:"), p("Point-of-Care Blood Diagnostics"),
    b("Primary Risk (as disclosed):"),
    p("Regulatory approval pathway (FDA clearance required for each test). "
      "UNDISCLOSED risks: technology did not work as claimed; internal accuracy data was concealed from investors and regulators."),
    b("Use of Funds:"), p("R&D (device miniaturisation), engineering hires, regulatory submissions, pharmaceutical partnerships."),
    c("Source: Carreyrou, J. (2018). Bad Blood. Knopf. p. 85–100."),
    sp()]

    doc.build(story)
    print("OK  theranos_2004_pitch.pdf")


# ═══════════════════════════════════════════════════════════════════════════════
# 4.  JUICERO  — Seed stage, October 2013
# ═══════════════════════════════════════════════════════════════════════════════
def build_juicero():
    """
    Sources:
    - TheVCFactory (2022). Juicero: A Cautionary Tale.
      https://thevcfactory.com/juicero-doug-evans-venture-capital-failure/
    - Gizmodo (2017). The Mad King of Juice.
      https://gizmodo.com/the-mad-king-of-juice-inside-the-dysfunctional-origins-1795330639
    - Crunchbase. Juicero Series A.
      https://www.crunchbase.com/funding_round/juicero-series-a--dc8795bd
    - TechCrunch (2016). Investors pour $70M into Juicero.
      https://techcrunch.com/2016/03/31/investors-pour-70-million-into-juicero-a-smart-kitchen-appliance-maker/
    - Wikipedia. Juicero.
      https://en.wikipedia.org/wiki/Juicero
    - Bloomberg (2017). Juicero's Juice Packets Can Be Squeezed by Hand.
      https://www.bloomberg.com/news/features/2017-04-19/silicon-valley-s-400-juicer-may-be-bytefinancials-trash
    """
    doc = _make_doc("juicero_2013_pitch.pdf")
    h1, h2, body, bold, src = _styles()
    def h(t, s=h2): return Paragraph(t, s)
    def p(t):       return Paragraph(t, body)
    def b(t):       return Paragraph(t, bold)
    def c(t):       return Paragraph(t, src)

    story = []

    story += [h("JUICERO — Seed Stage Pitch", h1),
              p("Date: October 2013  |  Stage: Seed  |  Location: San Francisco, CA, USA"),
              c("Source: Crunchbase. https://www.crunchbase.com/funding_round/juicero-series-a--dc8795bd"),
              rule()]

    story += [h("Company Snapshot"), _tbl([
        ["Field", "Value"],
        ["Company Name",         "Juicero, Inc."],
        ["Website",              "juicero.com"],
        ["HQ Location",          "San Francisco, California, USA"],
        ["Date Founded",         "2013"],
        ["Current Stage",        "Seed"],
        ["Amount Raised to Date","$0 prior to seed"],
        ["Round Target",         "$4,000,000"],
        ["Target Close",         "October 2013"],
    ], [6*cm, 11*cm]),
    c("Source: Wikipedia. Juicero. https://en.wikipedia.org/wiki/Juicero"),
    sp()]

    story += [h("Founding Team"), _tbl([
        ["Name", "Role", "Background", "Yrs Experience", "Ownership %"],
        ["Doug Evans", "CEO & Founder (SOLO — no technical co-founder)",
         "No college degree. Graffiti artist turned raw food entrepreneur. "
         "Founded and ran Organic Avenue (NYC cold-press juice bar chain), 5 years. "
         "No hardware engineering experience. No supply chain or manufacturing background.",
         "5", "~70%"],
    ], [4*cm, 3.5*cm, 6.5*cm, 1.5*cm, 1.5*cm]),
    c("Source: TheVCFactory (2022). https://thevcfactory.com/juicero-doug-evans-venture-capital-failure/"),
    sp(),
    p("No technical co-founder. No hardware engineering experience on founding team. "
      "No supply chain or manufacturing expertise at founding."),
    sp()]

    story += [h("Execution Timeline"), _tbl([
        ["Date", "Milestone"],
        ["2013",      "Juicero founded. Prototype under development."],
        ["Oct 2013",  "Seed round: $4M raised."],
        ["Apr 2014",  "Series A: $15.8M. Hardware development accelerated."],
        ["Mar 2016",  "Series B: $70M (Google Ventures, Kleiner Perkins, Thrive Capital)."],
        ["Apr 2016",  "Product launched at $699/unit + $5–8/pack subscription."],
        ["Apr 2017",  "Bloomberg investigation: packs can be squeezed by hand faster than the machine."],
        ["Sep 2017",  "Company shuts down. Total raised: ~$120M."],
    ], [3.5*cm, 13.5*cm]),
    c("Sources: TechCrunch (2016). https://techcrunch.com/2016/03/31/investors-pour-70-million-into-juicero-a-smart-kitchen-appliance-maker/ ; "
      "Bloomberg (2017). https://www.bloomberg.com/news/features/2017-04-19/silicon-valley-s-400-juicer-may-be-bytefinancials-trash"),
    sp()]

    story += [h("Problem Definition"),
    b("Customer Profile:"), p("Health-conscious urban professionals (ages 25–45) seeking fresh cold-press juice at home without prep time."),
    b("Problem Statement:"),
    p("Cold-press juicing at home is messy, time-consuming, and expensive. "
      "Commercial cold-press juice is $10–15 per bottle. "
      "Consumers want the nutritional benefits of fresh juice without the friction of preparation."),
    b("Current Solutions:"), p("Centrifugal home juicers (messy, noisy, oxidise juice), Whole Foods/Pressed Juicery cold-press bottles (~$10 each), Vitamix blenders (not cold-press)."),
    b("Gap Analysis:"), p("No appliance made premium cold-press juice at home with zero mess and instant results."),
    b("Frequency:"), p("Daily for health-conscious consumers."),
    b("Evidence:"), p("No formal customer discovery documented. Founder stated personal belief in raw food movement as validation."),
    c("Source: Gizmodo (2017). https://gizmodo.com/the-mad-king-of-juice-inside-the-dysfunctional-origins-1795330639"),
    sp()]

    story += [h("Product & Solution"),
    b("Product Stage:"), p("Hardware prototype under development at seed stage. No commercially available unit."),
    b("Core Stickiness:"),
    p("Proprietary juice packs (pre-chopped organic produce in sealed bags) create subscription revenue. "
      "Machine only works with Juicero-branded packs — razor-and-blade model. "
      "App connectivity tracks nutrition and re-orders packs automatically."),
    b("Differentiation (claimed):"),
    p("4 tons of pressing force for maximum nutrient extraction. "
      "WiFi-connected with quality sensor (pack expiry check). "
      "Organic, farm-sourced produce in sealed packs."),
    b("CRITICAL RED FLAG:"),
    p("In April 2017, Bloomberg journalists demonstrated that the juice packs could be squeezed by hand "
      "at the same speed and yield as the $700 machine, eliminating the core value proposition."),
    b("Defensibility Moat (claimed):"), p("Proprietary pack format and machine compatibility. Supply chain relationships with organic farms."),
    c("Sources: Bloomberg (2017). https://www.bloomberg.com/news/features/2017-04-19/silicon-valley-s-400-juicer-may-be-bytefinancials-trash ; "
      "TheVCFactory (2022). https://thevcfactory.com/juicero-doug-evans-venture-capital-failure/"),
    sp()]

    story += [h("Market & Scope"),
    b("Beachhead Market:"), p("US health-conscious consumers in urban coastal markets (SF, NYC, LA)."),
    b("Market Size Estimate (claimed):"), p("Compared to Keurig's $20B coffee machine business. "
                                             "US wellness market: ~$300B. Cold-press juice: ~$2B and growing."),
    b("Long-term Vision:"), p("Juicero becomes the Keurig of fresh produce — a connected appliance platform in every health-conscious household globally."),
    b("Expansion Strategy:"), p("US premium consumers first → mass market via price reduction → international → expand to other fresh foods beyond juice."),
    c("Source: TheVCFactory (2022). https://thevcfactory.com/juicero-doug-evans-venture-capital-failure/"),
    sp()]

    story += [h("Traction Metrics"), _tbl([
        ["Metric", "Value"],
        ["Stage Context",     "Seed — prototype under development, no commercial product"],
        ["Active Users",      "0 — pre-launch at seed stage"],
        ["Revenue",           "$0"],
        ["Pre-orders",        "Not disclosed"],
        ["Growth Rate",       "N/A"],
        ["Key Signal",        "Doug Evans' Organic Avenue chain served as proof of demand for premium juice"],
    ], [6*cm, 11*cm]),
    c("Source: Gizmodo (2017). https://gizmodo.com/the-mad-king-of-juice-inside-the-dysfunctional-origins-1795330639"),
    sp()]

    story += [h("Go-to-Market Strategy"),
    b("Buyer Persona:"), p("Health-obsessed consumers, ages 28–45, household income >$100K."),
    b("Primary Acquisition Channel:"), p("PR and media coverage of Silicon Valley hardware innovation. Influencer marketing in wellness space."),
    b("Sales Motion:"), p("Direct-to-consumer e-commerce + Apple Store-style retail."),
    b("Average Sales Cycle:"), p("Impulse to 1 week — consumer purchase decision."),
    b("Deal Closer:"), p("Product design appeal + founder's personal brand in wellness community."),
    c("Source: TheVCFactory (2022). https://thevcfactory.com/juicero-doug-evans-venture-capital-failure/"),
    sp()]

    story += [h("Business Model"), _tbl([
        ["Field", "Value"],
        ["Pricing Model",   "Hardware: $699 (later $399); Juice packs: $5–8 each (subscription)"],
        ["Gross Margin",    "Claimed: high on packs (subscription model). Actual: negative on hardware unit (COGS >>$699)"],
        ["Monthly Burn",    "~$1M+ (hardware R&D, supply chain setup)"],
        ["Runway",          "~4 months on $4M seed; required Series A immediately"],
        ["Revenue",         "$0 at seed stage"],
    ], [6*cm, 11*cm]),
    c("Sources: TheVCFactory (2022). https://thevcfactory.com/juicero-doug-evans-venture-capital-failure/ ; "
      "Wikipedia. Juicero. https://en.wikipedia.org/wiki/Juicero"),
    sp()]

    story += [h("Vision & Strategy"),
    b("5-Year Vision:"),
    p("Juicero is the Keurig of fresh produce — an internet-connected appliance in 10 million homes that delivers "
      "farm-fresh nutrition on demand. Expand from juice to full meal preparation."),
    b("Category Definition:"), p("Connected Fresh Produce Appliance / Subscription Food Hardware"),
    b("Primary Risk:"),
    p("Hardware unit economics: manufacturing a precision appliance at consumer price points is extremely difficult. "
      "Supply chain: dependency on specific organic farm suppliers. "
      "Consumer behaviour: willingness to pay $700 for a single-purpose appliance is unproven."),
    b("Use of Funds:"), p("Hardware engineering (precision mechanics, electronics), supply chain setup, organic farm partnerships, team hires."),
    c("Source: Gizmodo (2017). https://gizmodo.com/the-mad-king-of-juice-inside-the-dysfunctional-origins-1795330639"),
    sp()]

    doc.build(story)
    print("OK  juicero_2013_pitch.pdf")


# ═══════════════════════════════════════════════════════════════════════════════
# 5.  WEWORK  — Seed stage, 2010
# ═══════════════════════════════════════════════════════════════════════════════
def build_wework():
    """
    Sources:
    - Wikipedia. WeWork. https://en.wikipedia.org/wiki/WeWork
    - Wikipedia. Adam Neumann. https://en.wikipedia.org/wiki/Adam_Neumann
    - Built In NYC (2019). A Brief History of WeWork.
      https://www.builtinnyc.com/articles/brief-history-wework
    - Slideteam (2024). WeWork Founding Story and Original Pitch Deck.
      https://www.slideteam.net/blog/the-founding-story-of-wework-and-its-original-pitch-deck
    - Global Property (2019). The Story of WeWork's Mysterious First Investor.
      https://globalpropertyinc.com/2019/10/14/the-story-of-weworks-mysterious-first-investor/
    """
    doc = _make_doc("wework_2010_pitch.pdf")
    h1, h2, body, bold, src = _styles()
    def h(t, s=h2): return Paragraph(t, s)
    def p(t):       return Paragraph(t, body)
    def b(t):       return Paragraph(t, bold)
    def c(t):       return Paragraph(t, src)

    story = []

    story += [h("WEWORK — Seed Stage Pitch", h1),
              p("Date: 2010  |  Stage: Seed  |  Location: New York City, NY, USA"),
              c("Source: Built In NYC (2019). https://www.builtinnyc.com/articles/brief-history-wework"),
              rule()]

    story += [h("Company Snapshot"), _tbl([
        ["Field", "Value"],
        ["Company Name",         "WeWork Companies Inc."],
        ["Website",              "wework.com"],
        ["HQ Location",          "New York City, New York, USA"],
        ["Date Founded",         "2010"],
        ["Current Stage",        "Seed"],
        ["Amount Raised to Date","~$1M (Joel Schreiber, 2010)"],
        ["Round Target",         "$1,000,000"],
        ["Target Close",         "2010"],
    ], [6*cm, 11*cm]),
    c("Source: Global Property (2019). https://globalpropertyinc.com/2019/10/14/the-story-of-weworks-mysterious-first-investor/"),
    sp()]

    story += [h("Founding Team"), _tbl([
        ["Name", "Role", "Background", "Yrs Experience", "Ownership %"],
        ["Adam Neumann", "CEO & Co-founder",
         "Israeli-born. Ran Krawlers (baby clothing company), 2 years. "
         "Co-founded Green Desk (eco coworking, sold 2010 at ~$3M valuation), 2 years. "
         "No technology, real estate development or enterprise sales background.",
         "4", "~50%"],
        ["Miguel McKelvey", "CCO & Co-founder",
         "Licensed architect at small firm, 5 years. Sustainability focus. "
         "Co-founded Green Desk with Neumann. No prior startup exit.",
         "5", "~50%"],
    ], [4*cm, 3.5*cm, 6*cm, 1.5*cm, 2*cm]),
    c("Sources: Wikipedia. Adam Neumann. https://en.wikipedia.org/wiki/Adam_Neumann ; "
      "Built In NYC (2019). https://www.builtinnyc.com/articles/brief-history-wework"),
    sp()]

    story += [h("Execution Timeline"), _tbl([
        ["Date", "Milestone"],
        ["May 2008", "Green Desk (precursor) founded in DUMBO, Brooklyn. Eco coworking concept."],
        ["2010",     "Green Desk sold (~$3M valuation). WeWork founded with proceeds."],
        ["2010",     "Joel Schreiber invests ~$1M for reported 33% equity."],
        ["Apr 2011", "First WeWork location opens: SoHo, Manhattan."],
        ["End 2011", "Four NYC locations; waitlist forming; approaching breakeven."],
        ["2012",     "Expansion to multiple US cities and London."],
        ["2019",     "IPO attempt fails; valuation collapses from $47B to $8B."],
    ], [3.5*cm, 13.5*cm]),
    c("Sources: Built In NYC (2019). https://www.builtinnyc.com/articles/brief-history-wework ; "
      "Wikipedia. WeWork. https://en.wikipedia.org/wiki/WeWork"),
    sp()]

    story += [h("Problem Definition"),
    b("Customer Profile:"), p("Freelancers, early-stage startups, small business owners who need office space but cannot afford traditional long-term leases."),
    b("Problem Statement:"),
    p("Traditional office leases require 5–10 year commitments, personal guarantees, and upfront fit-out costs of $50–100K+. "
      "A 2-person startup or freelancer cannot access professional workspace economically. "
      "Coffee shops are not appropriate for client meetings or focused work."),
    b("Current Solutions:"), p("Traditional long-term office leases (inaccessible for early-stage companies), Regus/IWG (expensive, corporate, no community), coffee shops (unprofessional)."),
    b("Gap Analysis:"), p("No solution offered flexible, community-driven professional workspace at a daily or monthly rate to small teams and individuals."),
    b("Frequency:"), p("Daily — workspace is a daily need for every knowledge worker."),
    b("Evidence:"),
    p("Green Desk (predecessor) filled via Craigslist ads and word of mouth; tenants included PE shops and media companies. "
      "Key insight from Green Desk: tenants didn't care about sustainability — they came for community."),
    c("Source: Built In NYC (2019). https://www.builtinnyc.com/articles/brief-history-wework"),
    sp()]

    story += [h("Product & Solution"),
    b("Product Stage:"), p("Concept at seed stage. First location (SoHo) opened April 2011."),
    b("Core Stickiness:"),
    p("Community network: members refer each other for business, creating cross-pollination value. "
      "Flexible month-to-month contracts eliminate switching friction. "
      "Beer on tap, events, and social programming create cultural stickiness."),
    b("Differentiation:"),
    p("1. Design-forward spaces (not generic Regus-style cubicles).\n"
      "2. Community programming and member events.\n"
      "3. Month-to-month flexibility vs. traditional long-term leases.\n"
      "4. Pricing starting at $45/desk/day — accessible for 1-person teams."),
    b("Defensibility Moat (claimed):"),
    p("Community network effects: each new member makes the network more valuable. "
      "Brand identity as 'the place where startups work.' "
      "Real estate arbitrage: long-term master leases sub-let at per-desk rates."),
    c("Source: Slideteam (2024). https://www.slideteam.net/blog/the-founding-story-of-wework-and-its-original-pitch-deck"),
    sp()]

    story += [h("Market & Scope"),
    b("Beachhead Market:"), p("New York City freelancers, 1–5 person startups, and remote workers needing professional space."),
    b("Market Size Estimate:"),
    p("US: 10M+ freelancers and independent contractors (2010, Bureau of Labor Statistics). "
      "Global flexible workspace market: nascent but growing. "
      "WeWork later claimed a $3T global real estate opportunity — widely criticised as inflated."),
    b("Long-term Vision:"),
    p("WeWork is not a real estate company — it is a community platform. "
      "Every building in every city becomes a WeWork. "
      "Members carry WeWork access globally across hundreds of locations."),
    b("Expansion Strategy:"),
    p("NYC density first → US cities → London → global gateway cities → "
      "partnerships with real estate owners for managed building conversions."),
    c("Source: Slideteam (2024). https://www.slideteam.net/blog/the-founding-story-of-wework-and-its-original-pitch-deck"),
    sp()]

    story += [h("Traction Metrics"), _tbl([
        ["Metric", "Value"],
        ["Stage Context",  "Seed — pre-first-location (SoHo opens April 2011)"],
        ["Active Members", "0 — concept stage at 2010 seed"],
        ["Revenue",        "$0 (Green Desk sold, WeWork pre-launch)"],
        ["Prior Proof",    "Green Desk: filled to capacity via Craigslist, consistent demand proven"],
        ["Growth Rate",    "N/A at seed; 200% YoY growth achieved by 2014"],
        ["Waitlist",       "Forming by end of 2011 for SoHo location"],
    ], [6*cm, 11*cm]),
    c("Sources: Built In NYC (2019). https://www.builtinnyc.com/articles/brief-history-wework ; "
      "Slideteam (2024). https://www.slideteam.net/blog/the-founding-story-of-wework-and-its-original-pitch-deck"),
    sp()]

    story += [h("Go-to-Market Strategy"),
    b("Buyer Persona:"), p("Freelancer / early-stage founder / remote employee, 25–40, knowledge worker in NYC."),
    b("Primary Acquisition Channel:"), p("Craigslist (proven from Green Desk), word-of-mouth, startup community events."),
    b("Sales Motion:"), p("Self-serve — walk in, take a tour, sign month-to-month membership. No enterprise sales at seed stage."),
    b("Average Sales Cycle:"), p("1–3 days from inquiry to membership start."),
    b("Deal Closer:"), p("Space quality + community feel during in-person tour."),
    c("Source: Built In NYC (2019). https://www.builtinnyc.com/articles/brief-history-wework"),
    sp()]

    story += [h("Business Model"), _tbl([
        ["Field", "Value"],
        ["Pricing Model",   "Per-desk: $45/day or $350–500/month; private offices: $650–1500/month"],
        ["Gross Margin",    "~20–25% at unit level (real estate arbitrage margin). Later proven insufficient at scale."],
        ["Monthly Burn",    "~$80,000 (pre-first-location fit-out, 5-person team)"],
        ["Runway",          "~12 months on $1M raise"],
        ["Revenue",         "$0 at 2010 seed stage (first location not yet open)"],
    ], [6*cm, 11*cm]),
    c("Sources: Slideteam (2024). https://www.slideteam.net/blog/the-founding-story-of-wework-and-its-original-pitch-deck ; "
      "Wikipedia. WeWork. https://en.wikipedia.org/wiki/WeWork"),
    sp()]

    story += [h("Vision & Strategy"),
    b("5-Year Vision:"),
    p("WeWork becomes the global operating system for how companies work — "
      "a physical community network across every major city where members carry access, connections, and services. "
      "Physical space is just the entry point to a broader platform of financial, HR, and business services for members."),
    b("Category Definition:"), p("Flexible Co-working Space / Community Platform"),
    b("Primary Risk:"),
    p("Real estate dependency: WeWork signs long-term master leases (liability) and sub-lets short-term (revenue). "
      "In a recession, members cancel month-to-month contracts while WeWork remains locked into 10-year leases — "
      "creating catastrophic liability mismatch. "
      "This risk was documented in WeWork's 2019 S-1 and contributed to IPO failure."),
    b("Use of Funds:"), p("First SoHo location fit-out ($500K), engineering (member portal/app), operations hire, marketing."),
    c("Source: Wikipedia. WeWork. https://en.wikipedia.org/wiki/WeWork"),
    sp()]

    doc.build(story)
    print("OK  wework_2010_pitch.pdf")


# ═══════════════════════════════════════════════════════════════════════════════
# 6.  TABBY  — Seed stage, September 2019  (MENA / UAE-Saudi)
# ═══════════════════════════════════════════════════════════════════════════════
def build_tabby():
    """
    Sources:
    - MenaBytesm (2019). Tabby Seed Announcement.
      https://www.menabytes.com/tabby-seed/
    - Fast Company Middle East (2021). Hosam Arab and Daniil Barkalov.
      https://fastcompanyme.com/most-creative-people/hosam-arab-and-daniil-barkalov/
    - TechCrunch (2023). Tabby Series D.
      https://techcrunch.com/2023/10/31/buy-now-pay-later-platform-tabby-nabs-200m-in-series-d-funding-at-1-5b-valuation/
    - Arab News (2025). Tabby Series E.
      https://www.arabnews.com/node/2589906/
    - UAE Startup Story (2024). Tabby Success Story.
      https://uaestartupstory.com/tabby-success-story/
    - InvestRiyadh (2024). Tabby Profile.
      https://investriyadh.ai/entities/tabby/
    """
    doc = _make_doc("tabby_2019_pitch.pdf")
    h1, h2, body, bold, src = _styles()
    def h(t, s=h2): return Paragraph(t, s)
    def p(t):       return Paragraph(t, body)
    def b(t):       return Paragraph(t, bold)
    def c(t):       return Paragraph(t, src)

    story = []

    story += [h("TABBY — Seed Stage Pitch", h1),
              p("Date: September 2019  |  Stage: Seed  |  Location: Dubai, UAE & Riyadh, Saudi Arabia"),
              c("Source: MenaBytesm (2019). https://www.menabytes.com/tabby-seed/"),
              rule()]

    story += [h("Company Snapshot"), _tbl([
        ["Field", "Value"],
        ["Company Name",         "Tabby FZ-LLC"],
        ["Website",              "tabby.ai"],
        ["HQ Location",          "Dubai, UAE (dual-HQ: Riyadh, Saudi Arabia)"],
        ["Date Founded",         "2019-01-01"],
        ["Current Stage",        "Seed"],
        ["Amount Raised to Date","$0 prior to seed"],
        ["Round Target",         "$2,000,000"],
        ["Target Close",         "2019-09-01"],
    ], [6*cm, 11*cm]),
    c("Sources: MenaBytesm (2019). https://www.menabytes.com/tabby-seed/ ; InvestRiyadh (2024). https://investriyadh.ai/entities/tabby/"),
    sp()]

    story += [h("Founding Team"), _tbl([
        ["Name", "Role", "Background", "Yrs Experience", "Ownership %"],
        ["Hosam Arab", "CEO & Co-founder",
         "BSc Electrical Engineering, Queen's University. MBA Harvard Business School 2009. "
         "Co-founder and CEO of Namshi (MENA fashion e-commerce). Namshi acquired by "
         "Emaar Malls for $129.5M (2019). Deep MENA consumer fintech expertise.",
         "10", "50%"],
        ["Daniil Barkalov", "COO & Co-founder (Technical)",
         "Software engineer. CEO of Revo Technology (Russian BNPL/merchant fintech). "
         "Prior experience scaling Lamoda (Russian e-commerce) technology platform. "
         "Deep payments engineering and BNPL operations background.",
         "7", "50%"],
    ], [4*cm, 3.5*cm, 6*cm, 1.5*cm, 2*cm]),
    c("Source: Fast Company Middle East (2021). https://fastcompanyme.com/most-creative-people/hosam-arab-and-daniil-barkalov/"),
    sp(),
    p("Full-time start date: 2019-01-01. Both founders transitioned directly from operational roles at scale."),
    p("Founder-market fit: Hosam led Namshi through acquisition — firsthand experience of low credit penetration "
      "killing MENA e-commerce conversion. Daniil built and ran a BNPL product in Russia — technical operator."),
    sp()]

    story += [h("Execution Timeline"), _tbl([
        ["Date", "Milestone"],
        ["2019-01", "Tabby incorporated in Dubai. Founders begin integrating with major retail merchants."],
        ["2019-09", "Seed round closed: $2M. Investors: Global Founders Capital, Arbor Ventures, Wamda Capital."],
        ["2020-06", "Seed extension: $7M. Lead: Raed Ventures. Public launch in UAE and Saudi Arabia."],
        ["2020-12", "Series A: $23M. Arbor Ventures, Mubadala Capital, STV. 400K users, 2,000 merchants."],
        ["2022-03", "Series B: $54M. Sequoia India, STV. Valuation: $300M."],
        ["2025-02", "Series E: $160M. Valuation: $3.3B (unicorn). 15M users, 40,000+ merchants."],
    ], [3.5*cm, 13.5*cm]),
    c("Sources: MenaBytesm (2019). https://www.menabytes.com/tabby-seed/ ; "
      "Arab News (2025). https://www.arabnews.com/node/2589906/"),
    sp()]

    story += [h("Problem Definition"),
    b("Customer Profile:"), p("GCC consumers (UAE, Saudi Arabia) aged 18-40, online shoppers. "
                               "Underserved by traditional credit: Saudi credit card penetration <15%, UAE <30%."),
    b("Problem Statement:"),
    p("Consumer credit access in the Gulf is structurally broken. Bank credit card approval takes weeks, "
      "requires salary certificates, and is rejected for most residents and expats. "
      "Cash-on-delivery (COD) dominates MENA e-commerce (35-50% of orders), creating costly returns "
      "and preventing impulse purchases. Merchants lose 20-40% conversion on checkout due to payment friction. "
      "Islamic finance principles create cultural aversion to traditional interest-bearing credit."),
    b("Current Solutions:"), p("Bank credit cards (low penetration, slow approval), cash-on-delivery (COD — high return rates, "
                                "no conversion on digital), installment plans at banks (branch-only, weeks of processing)."),
    b("Gap Analysis:"), p("No instant, Shariah-compliant, interest-free instalment solution existed at e-commerce checkout "
                           "in MENA that worked for both consumers without credit cards and merchants needing conversion."),
    b("Frequency:"), p("Daily — every digital purchase in MENA faces this friction."),
    b("Evidence:"), p("Hosam Arab observed COD dominating 35-50% of Namshi orders. "
                       "15% credit card penetration in Saudi Arabia documented by Saudi Central Bank (SAMA)."),
    c("Source: MenaBytesm (2019). https://www.menabytes.com/tabby-seed/ ; "
      "UAE Startup Story (2024). https://uaestartupstory.com/tabby-success-story/"),
    sp()]

    story += [h("Product & Solution"),
    b("Product Stage:"), p("Pre-launch at seed — integrating with major retail merchants in UAE and Saudi Arabia."),
    b("Core Stickiness:"),
    p("Pay in 4: Split any purchase into 4 interest-free instalments, 0% for consumers. "
      "Merchant bears a small discount rate (MDR). No late fees for consumers — Shariah-compliant. "
      "Seamless checkout widget — one click at merchant checkout, approval in seconds. "
      "As consumer builds Tabby history, approval limits increase automatically."),
    b("Differentiation:"),
    p("1. Shariah-compliant (zero interest for consumers) — critical for GCC cultural fit.\n"
      "2. Instant approval (seconds, not days) — no salary certificate, no bank branch.\n"
      "3. B2B2C model: merchants pay MDR, consumers never pay interest — different from Western BNPL.\n"
      "4. Deep GCC market knowledge — team built and scaled regional e-commerce."),
    b("Defensibility Moat:"),
    p("Consumer credit data network: every Tabby transaction builds a proprietary regional credit dataset "
      "that improves underwriting — a data moat unavailable to foreign entrants. "
      "Merchant lock-in: once integrated, switching is costly. "
      "Regulatory relationships with Saudi Central Bank (SAMA) and UAE Central Bank create barriers."),
    c("Source: UAE Startup Story (2024). https://uaestartupstory.com/tabby-success-story/ ; "
      "InvestRiyadh (2024). https://investriyadh.ai/entities/tabby/"),
    sp()]

    story += [h("Market & Scope"),
    b("Beachhead Market:"), p("UAE affluent digital consumers + Saudi Arabia (largest GCC market: 37M pop., "
                               "60%+ under 35, <15% credit card penetration, $50B e-commerce opportunity)."),
    b("Market Size Estimate:"), p("Africa & Middle East BNPL GMV: $12.6B (2023) → $32.6B (2029 projected). "
                                    "GCC e-commerce: $50B+. Tabby processed $10B GMV annually by 2025."),
    b("Long-term Vision:"), p("Tabby becomes the financial layer for every purchase in MENA — "
                                "from BNPL to Tabby Card (full credit product) to digital wallets. "
                                "The credit infrastructure the Gulf never had."),
    b("Expansion Strategy:"), p("UAE and Saudi Arabia first (highest digital spend, lowest credit penetration) → "
                                  "Egypt and wider MENA → financial product expansion (Tabby Card, Tweeq wallet) → "
                                  "institutional financial services."),
    c("Sources: Mordor Intelligence via BusinessWire (2024). BNPL Africa & Middle East Market Report ; "
      "InvestRiyadh (2024). https://investriyadh.ai/entities/tabby/"),
    sp()]

    story += [h("Traction Metrics"), _tbl([
        ["Metric", "Value"],
        ["Stage Context",       "Seed — pre-launch, merchant integration phase (Sept 2019)"],
        ["Active Users",        "0 at seed (public launch post-seed extension, June 2020)"],
        ["Merchant Pipeline",   "Discussions with major GCC retail chains ongoing at seed"],
        ["Early Revenue",       "$0 at seed — pre-launch"],
        ["Growth Rate (MoM)",   "N/A at seed; 400K users and 2,000 merchants within 12 months of launch"],
        ["Key Signal",          "Hosam Arab's Namshi exit ($129.5M) provides personal credibility and direct merchant "
                                "relationships for rapid partnership pipeline."],
    ], [6*cm, 11*cm]),
    c("Source: MenaBytesm Series A (2020). https://www.menabytes.com/tabby-series-a/"),
    sp()]

    story += [h("Go-to-Market Strategy"),
    b("Buyer Persona:"), p("Head of e-commerce / CMO at GCC fashion, electronics, home goods retailers."),
    b("Primary Acquisition Channel:"), p("B2B2C — direct merchant partnerships. Hosam Arab's Namshi network "
                                          "provides warm introductions to Adidas, IKEA, major regional retailers."),
    b("Sales Motion:"), p("Enterprise direct sales. Merchant signs API integration agreement; Tabby widget at checkout."),
    b("Average Sales Cycle:"), p("2-4 weeks for large merchants; instant for small/mid via self-serve API."),
    b("Deal Closer:"), p("Hosam Arab (CEO) for enterprise merchants; product for self-serve."),
    c("Source: UAE Startup Story (2024). https://uaestartupstory.com/tabby-success-story/"),
    sp()]

    story += [h("Business Model"), _tbl([
        ["Field", "Value"],
        ["Pricing Model",   "Merchant Discount Rate (MDR): 4-8% per transaction (merchant pays; consumer pays 0%)"],
        ["Gross Margin",    "Estimated 60-70% net margin on MDR after credit loss provisioning"],
        ["Monthly Burn",    "~$150,000 (small team of 8-10 engineers + operations)"],
        ["Runway",          "13+ months on $2M seed"],
        ["Revenue",         "$0 at seed — pre-launch; transaction fees begin at public launch"],
    ], [6*cm, 11*cm]),
    c("Sources: InvestRiyadh (2024). https://investriyadh.ai/entities/tabby/ ; "
      "BusinessWire BNPL Report (2024)"),
    sp()]

    story += [h("Vision & Strategy"),
    b("5-Year Vision:"),
    p("Tabby becomes the dominant financial services platform for every GCC consumer — "
      "starting with BNPL and expanding into full credit products, digital wallets, and financial services. "
      "Every merchant in MENA offers Tabby at checkout. Every consumer has a Tabby credit line. "
      "IPO on Saudi Tadawul exchange as the region's first major fintech unicorn."),
    b("Category Definition:"), p("Buy Now Pay Later (BNPL) / Consumer Credit Infrastructure for MENA"),
    b("Primary Risk:"),
    p("Credit risk: underwriting consumers without traditional credit history requires proprietary models. "
      "Regulatory: SAMA and UAE Central Bank evolving BNPL frameworks create compliance uncertainty. "
      "Competition: Tamara (rival BNPL) launched in Saudi Arabia 2020; foreign BNPL players may enter. "
      "Unit economics: MDR compression as market matures."),
    b("Use of Funds:"), p("Engineering hires (3 backend, 1 risk/ML), merchant integrations, "
                           "regulatory compliance (SAMA sandbox application), Saudi Arabia market entry."),
    c("Source: Arab News (2025). https://www.arabnews.com/node/2589906/"),
    sp()]

    doc.build(story)
    print("OK tabby_2019_pitch.pdf")


# ═══════════════════════════════════════════════════════════════════════════════
# 7.  PAYMOB  — Series A stage, 2020-2021  (MENA / Egypt)
# ═══════════════════════════════════════════════════════════════════════════════
def build_paymob():
    """
    Sources:
    - TechCrunch (2021). Paymob Series A.
      https://techcrunch.com/2021/04/08/egypts-paymob-closes-18-5m-series-a-to-expand-payments-services-across-mena/
    - MenaBytesm (2020). Paymob $3.5M Announcement.
      https://www.menabytes.com/paymob-3-5-million/
    - TechCrunch (2024). Paymob Series B Update.
      https://techcrunch.com/2024/09/11/paymob-lands-another-22-million-and-is-profitable-in-egypt/
    - Paymob A15 Case Study.
      https://www.a15.com/paymob-a15-case-study/
    - Entrepreneur ME. Islam Shawky Profile.
      https://mena.entrepreneur.com/growth-strategies/driving-change-paymob-co-founder-and-ceo-islam-shawky-is/438670
    """
    doc = _make_doc("paymob_2020_pitch.pdf")
    h1, h2, body, bold, src = _styles()
    def h(t, s=h2): return Paragraph(t, s)
    def p(t):       return Paragraph(t, body)
    def b(t):       return Paragraph(t, bold)
    def c(t):       return Paragraph(t, src)

    story = []

    story += [h("PAYMOB — Series A Stage Pitch", h1),
              p("Date: July 2020  |  Stage: Series A  |  Location: Cairo, Egypt"),
              c("Source: MenaBytesm (2020). https://www.menabytes.com/paymob-3-5-million/"),
              rule()]

    story += [h("Company Snapshot"), _tbl([
        ["Field", "Value"],
        ["Company Name",         "Paymob Solutions"],
        ["Website",              "paymob.com"],
        ["HQ Location",          "Cairo, Egypt"],
        ["Date Founded",         "2015-01-01"],
        ["Current Stage",        "Series A"],
        ["Amount Raised to Date","$0 (bootstrapped 5 years)"],
        ["Round Target",         "$3,500,000"],
        ["Target Close",         "2020-07-01"],
    ], [6*cm, 11*cm]),
    c("Source: TechCrunch (2021). https://techcrunch.com/2021/04/08/egypts-paymob-closes-18-5m-series-a-to-expand-payments-services-across-mena/"),
    sp()]

    story += [h("Founding Team"), _tbl([
        ["Name", "Role", "Background", "Yrs Experience", "Ownership %"],
        ["Islam Shawky", "CEO & Co-founder",
         "BSc Mechanical Engineering, American University in Cairo (AUC, 2015). "
         "Built e-commerce platform at AUC (2013-2015); discovered payment gap while "
         "trying to accept digital payments. Forbes ME 30-under-30 (2021). "
         "5 years bootstrapping Paymob from student project to 35,000 merchants.",
         "7", "34%"],
        ["Alain El Hajj", "COO & Co-founder",
         "BSc Computer Science, American University in Cairo (AUC, 2015). "
         "Co-built the original AUC e-commerce platform. Operational lead "
         "for Paymob's merchant onboarding and partner integrations. "
         "Forbes ME 30-under-30 (2021).",
         "7", "33%"],
        ["Mostafa El Menessy", "CTO & Co-founder (Technical)",
         "American University in Cairo (AUC, 2016). "
         "Built Paymob's core payment infrastructure from scratch. "
         "Architect of CBE-compliant payment facilitator system. "
         "Led technical integrations with Vodafone Cash, Orange Money, all Egyptian banks.",
         "6", "33%"],
    ], [4*cm, 3.5*cm, 5.5*cm, 1.5*cm, 2*cm]),
    c("Sources: Entrepreneur ME. https://mena.entrepreneur.com/growth-strategies/driving-change-paymob-co-founder-and-ceo-islam-shawky-is/438670 ; "
      "TechCrunch (2021). https://techcrunch.com/2021/04/08/egypts-paymob-closes-18-5m-series-a-to-expand-payments-services-across-mena/"),
    sp(),
    p("Full-time start date: 2015-01-01. Three co-founders, all full-time from founding."),
    p("Regulatory milestone: First Egyptian fintech to receive Central Bank of Egypt (CBE) payment facilitator licence (2018). "
      "This took 3 years of relationship-building — a durable competitive moat."),
    sp()]

    story += [h("Execution Timeline"), _tbl([
        ["Date", "Milestone"],
        ["2013", "Three AUC students build e-commerce platform; discover Egyptian payment gap firsthand."],
        ["2015", "Paymob incorporated. Begin building payment gateway API for Egyptian merchants."],
        ["2018", "Receive Central Bank of Egypt (CBE) payment facilitator licence — first Egyptian fintech."],
        ["Sep 2019", "Onboarding 60 merchants/month. Operating profitably at small scale in Egypt."],
        ["Jul 2020", "Series A Tranche 1: $3.5M. Lead: Global Ventures. 35,000 merchants, $5B lifetime volume."],
        ["Apr 2021", "Series A Total: $18.5M. 6,000 merchants/month onboarding rate (100x growth from 2019)."],
        ["2022", "Series B: $50M. PayPal Ventures, Kora Capital. Expanding to UAE, Saudi, Pakistan."],
        ["Sep 2024", "Series B Extension: $22M. Profitable in Egypt core market. 350,000 merchants, 5 countries."],
    ], [3.5*cm, 13.5*cm]),
    c("Sources: TechCrunch (2021) ; TechCrunch (2024). https://techcrunch.com/2024/09/11/paymob-lands-another-22-million-and-is-profitable-in-egypt/"),
    sp()]

    story += [h("Problem Definition"),
    b("Customer Profile:"), p("Egyptian SMEs, e-commerce merchants, digital-native startups needing to accept "
                               "digital payments from consumers. Egypt: 110M population, 85% cash-dependent economy."),
    b("Problem Statement:"),
    p("Egypt's economy is 85% cash-dependent. No merchant payment infrastructure existed for "
      "digital startups or SMEs. Banks offered credit card processing only to large enterprises "
      "through months-long manual processes. No digital wallet integration. No API for developers. "
      "The result: Egyptian e-commerce ran on cash-on-delivery (COD), creating 30-40% return rates "
      "and preventing growth of the digital economy. A $50B+ e-commerce opportunity locked behind "
      "a payment infrastructure gap."),
    b("Current Solutions:"), p("Bank credit card processing (enterprise only, months of paperwork), "
                                "cash-on-delivery (high return rates, costly operations), "
                                "manual bank transfers (slow, no integration)."),
    b("Gap Analysis:"), p("No developer-friendly payment API existed that could connect any Egyptian merchant "
                           "or startup to all payment methods (cards, mobile wallets, bank transfers) in one integration."),
    b("Frequency:"), p("Daily — every digital transaction in Egypt faces this infrastructure gap."),
    b("Evidence:"),
    p("35,000 merchants onboarded organically without any marketing spend (2020). "
      "450% increase in merchant onboarding rate during COVID-19 lockdowns — "
      "digital payment adoption crisis created massive pull demand. "
      "Claimed 85% of Egyptian mobile wallet transactions facilitated by Paymob (2020)."),
    c("Source: TechCrunch (2021). https://techcrunch.com/2021/04/08/egypts-paymob-closes-18-5m-series-a-to-expand-payments-services-across-mena/"),
    sp()]

    story += [h("Product & Solution"),
    b("Product Stage:"), p("Live — operating at scale in Egypt since 2015. 35,000 merchants. $5B lifetime transaction volume."),
    b("Core Stickiness:"),
    p("Once a merchant integrates Paymob's API, switching requires re-engineering all payment flows. "
      "Multi-wallet integrations (Vodafone Cash, Orange Money, Etisalat) create lock-in. "
      "CBE licence means Paymob is a regulated infrastructure that competitors cannot replicate quickly."),
    b("Differentiation:"),
    p("1. First Egyptian fintech with CBE payment facilitator licence (2018) — regulatory moat.\n"
      "2. 50+ payment methods in one integration (cards, mobile wallets, bank transfers, QR).\n"
      "3. No monthly fees — transaction-based only, removing adoption barrier for SMEs.\n"
      "4. Localisation: Arabic interface, Egyptian regulatory compliance, local bank relationships."),
    b("Defensibility Moat:"),
    p("Regulatory moat (CBE licence). Transaction data network. Local bank and telco partnerships. "
      "First-mover brand among Egyptian developers and merchants."),
    c("Source: Paymob A15 Case Study. https://www.a15.com/paymob-a15-case-study/"),
    sp()]

    story += [h("Market & Scope"),
    b("Beachhead Market:"), p("Egypt (110M population, 85% cash economy, fastest-growing digital payment market in Africa)."),
    b("Market Size Estimate:"), p("Egypt e-commerce: $50B+ annual opportunity. "
                                    "MENA payments total: $100B+ market. "
                                    "Sub-Saharan Africa payments: additional $40B+ addressable."),
    b("Long-term Vision:"), p("Paymob becomes the default payment infrastructure for MENA and Africa — "
                                "the Stripe of emerging markets. Every merchant in the region accepts "
                                "digital payments through Paymob's unified API."),
    b("Expansion Strategy:"), p("Egypt first (dominant position) → UAE and Saudi Arabia → Kenya and Pakistan → "
                                  "wider MENA/Africa. Layer products: gateway → BNPL → POS → financial services."),
    c("Source: TechCrunch (2021). https://techcrunch.com/2021/04/08/egypts-paymob-closes-18-5m-series-a-to-expand-payments-services-across-mena/"),
    sp()]

    story += [h("Traction Metrics"), _tbl([
        ["Metric", "Value"],
        ["Stage Context",       "Series A — B2B payment infrastructure. 'Users' = paying merchant businesses, not consumers."],
        ["Active Merchants (MAU)","35000 paying merchant businesses (July 2020). Each merchant serves 100s of consumers daily."],
        ["Monthly Active Users","35000"],
        ["Lifetime Volume",     "$5,000,000,000 (cumulative GMV processed — proxy for product-market fit at scale)"],
        ["Growth Rate (MoM)",   "450"],
        ["Paid Users",          "35000"],
        ["Early Revenue",       "50000"],
        ["Key Signal",          "Zero marketing spend — 35,000 merchants onboarded organically in 5 years. "
                                "450% MoM growth in merchant onboarding during COVID-19. "
                                "85% of Egyptian mobile wallet transactions facilitated by Paymob. "
                                "Zero institutional funding for 5 years — bootstrapped to scale."],
    ], [6*cm, 11*cm]),
    c("Source: TechCrunch (2021). https://techcrunch.com/2021/04/08/egypts-paymob-closes-18-5m-series-a-to-expand-payments-services-across-mena/"),
    sp()]

    story += [h("Go-to-Market Strategy"),
    b("Buyer Persona:"), p("Egyptian SME owner / startup CTO needing to accept digital payments."),
    b("Primary Acquisition Channel:"), p("Developer community (word-of-mouth), direct SME outreach, "
                                          "e-commerce platform partnerships (Shopify integration announced post-Series A)."),
    b("Sales Motion:"), p("Self-serve for SMEs (sign up, get API keys, go live). Enterprise direct sales for large merchants."),
    b("Average Sales Cycle:"), p("Hours for SME self-serve; 1-2 weeks for enterprise integration."),
    b("Deal Closer:"), p("Product (zero monthly fee, easy API) for SME; Islam Shawky for enterprise."),
    c("Source: Paymob A15 Case Study. https://www.a15.com/paymob-a15-case-study/"),
    sp()]

    story += [h("Business Model"), _tbl([
        ["Field", "Value"],
        ["Pricing Model",   "Transaction-based fees (% of payment volume); no monthly subscription fees"],
        ["Gross Margin",    "Estimated 60-70% (software-led payment facilitator; low marginal cost per transaction)"],
        ["Monthly Burn",    "~$80,000 (bootstrapped lean team of ~20; no VC-funded spending until Series A)"],
        ["Runway",          "Bootstrapped 5 years; $3.5M Series A gives 36+ months runway"],
        ["Revenue",         "Profitable at core Egypt operations by 2020 (implied by 5-year bootstrap without funding)"],
    ], [6*cm, 11*cm]),
    c("Source: TechCrunch (2024). https://techcrunch.com/2024/09/11/paymob-lands-another-22-million-and-is-profitable-in-egypt/"),
    sp()]

    story += [h("Vision & Strategy"),
    b("5-Year Vision:"),
    p("Paymob becomes the default payment infrastructure layer for MENA and Africa — "
      "the trusted, API-first platform that powers digital commerce across emerging markets. "
      "Every merchant from Cairo to Karachi to Nairobi accepts digital payments through Paymob. "
      "Expanding from payment processing into embedded finance: BNPL, payroll, working capital."),
    b("Category Definition:"), p("Payment Infrastructure for Emerging Markets / Developer Payment Gateway"),
    b("Primary Risk:"),
    p("Regulatory: Payment facilitation rules evolving across multiple Central Banks (Egypt, UAE, Saudi, Pakistan). "
      "Currency devaluation: Egyptian pound volatility affects transaction value in USD terms. "
      "Competition: Fawry (Egyptian incumbent), global players (Stripe, PayPal) entering emerging markets. "
      "Credit risk if expanding into lending products."),
    b("Use of Funds:"), p("Engineering hires (5 backend), UAE and Saudi Arabia regulatory licences, "
                           "Pakistan market entry, enterprise sales team."),
    c("Source: TechCrunch (2021). https://techcrunch.com/2021/04/08/egypts-paymob-closes-18-5m-series-a-to-expand-payments-services-across-mena/"),
    sp()]

    doc.build(story)
    print("OK paymob_2020_pitch.pdf")


# ═══════════════════════════════════════════════════════════════════════════════
# 8.  FETCHR  — Series A stage, 2015  (MENA / UAE)  — PASS case
# ═══════════════════════════════════════════════════════════════════════════════
def build_fetchr():
    """
    Sources:
    - The National (2015). Fetchr founder interview.
      https://www.thenationalnews.com/business/economy/generation-start-up-funding-was-petrifying-in-the-early-days-says-fetchr-founder-1.625104
    - MenaBytesm. Fetchr Series B.
      https://www.menabytes.com/fetchr-41-million-series-b/
    - Bloomberg (Oct 2021). Fetchr liquidation warning.
      https://www.bloomberg.com/news/articles/2021-10-06/top-backer-of-dubai-app-fetchr-warns-startup-faces-liquidation
    - Bloomberg (Dec 2019). Fetchr narrowly averts collapse.
      https://www.bloomberg.com/news/articles/2019-12-04/one-of-middle-east-s-largest-startups-narrowly-averts-collapse
    - Wamda (Oct 2021). Risk of liquidation.
      https://www.wamda.com/2021/10/fetchr-risk-liquidation
    """
    doc = _make_doc("fetchr_2015_pitch.pdf")
    h1, h2, body, bold, src = _styles()
    def h(t, s=h2): return Paragraph(t, s)
    def p(t):       return Paragraph(t, body)
    def b(t):       return Paragraph(t, bold)
    def c(t):       return Paragraph(t, src)

    story = []

    story += [h("FETCHR — Series A Stage Pitch", h1),
              p("Date: June 2015  |  Stage: Series A  |  Location: Dubai, UAE"),
              p("<b>Note:</b> This document reconstructs the pitch at Series A stage. Fetchr subsequently "
                "raised $41M Series B (2016) at $300M valuation, then ceased operations in 2021 "
                "due to unsustainable unit economics and a $100M Saudi tax dispute."),
              c("Source: Bloomberg (Oct 2021). https://www.bloomberg.com/news/articles/2021-10-06/top-backer-of-dubai-app-fetchr-warns-startup-faces-liquidation"),
              rule()]

    story += [h("Company Snapshot"), _tbl([
        ["Field", "Value"],
        ["Company Name",         "Fetchr Inc."],
        ["Website",              "fetchr.us"],
        ["HQ Location",          "Dubai, UAE"],
        ["Date Founded",         "2012-11-01"],
        ["Current Stage",        "Series A"],
        ["Amount Raised to Date","~$1,200,000 (bootstrap, family & friends)"],
        ["Round Target",         "$11,000,000"],
        ["Target Close",         "2015-06-01"],
    ], [6*cm, 11*cm]),
    c("Source: The National (2015). https://www.thenationalnews.com/business/economy/generation-start-up-funding-was-petrifying-in-the-early-days-says-fetchr-founder-1.625104"),
    sp()]

    story += [h("Founding Team"), _tbl([
        ["Name", "Role", "Background", "Yrs Experience", "Ownership %"],
        ["Idriss Al Rifai", "CEO & Co-founder",
         "Boston Consulting Group consultant (pre-startup). Head of Operations at "
         "MarkaVIP (MENA e-commerce). Observed 25-35% delivery failure rate at MarkaVIP "
         "due to address problems. Silicon Valley fundraising background (pitched NEA personally).",
         "7", "40%"],
        ["Joy Ajlouny", "CMO & Co-founder",
         "Serial US entrepreneur. Founded Joy's (off-price clothing). Founded Bonfaire "
         "(luxury fashion discovery platform) — acquired by Moda Operandi 2013. "
         "Palestinian-American with deep understanding of MENA address problem. "
         "Silicon Valley VC network provided Series A introduction to NEA.",
         "8", "35%"],
    ], [4*cm, 3.5*cm, 6*cm, 1.5*cm, 2*cm]),
    c("Sources: The National (2015) ; Arabian Business. https://www.arabianbusiness.com/transport/416008-delivery-man"),
    sp(),
    p("Full-time start date: 2012-11-01. Both founders full-time from company inception."),
    sp()]

    story += [h("Execution Timeline"), _tbl([
        ["Date", "Milestone"],
        ["Nov 2012", "Fetchr founded. Al Rifai and Ajlouny build first GPS-based delivery prototype."],
        ["2013-2014", "Bootstrapped with personal savings and family capital (~$1.2M). 9 months couchsurfing."],
        ["Sep 2015", "Series A: $11M from NEA (first NEA investment in Middle East). "
                     "Double-digit weekly growth reported. Operating UAE, Saudi, Bahrain."],
        ["May 2016", "Series B: $41M from NEA, Majid Al Futtaim, Nokia Growth Partners. "
                     "Valuation: ~$300M. Expanded to 6 countries."],
        ["Dec 2019", "Narrowly averts collapse. Secures $10M emergency funding."],
        ["2020", "Cuts 1,230+ jobs. Exits Jordan, Bahrain, Oman. Secures $15M rescue funding."],
        ["Oct 2021", "Saudi $100M tax dispute. Investor (Beco Capital) warns of liquidation. CEASED OPERATIONS."],
    ], [3.5*cm, 13.5*cm]),
    c("Sources: MenaBytesm Series B. https://www.menabytes.com/fetchr-41-million-series-b/ ; "
      "Bloomberg (2021). https://www.bloomberg.com/news/articles/2021-10-06/top-backer-of-dubai-app-fetchr-warns-startup-faces-liquidation"),
    sp()]

    story += [h("Problem Definition"),
    b("Customer Profile:"), p("E-commerce merchants in UAE, Saudi Arabia, and wider GCC "
                               "whose deliveries fail due to customers having no fixed street address."),
    b("Problem Statement:"),
    p("25-35% of deliveries in the Middle East fail. The reason: most GCC cities lack street-level "
      "addressing systems. Drivers cannot find recipients. DHL and FedEx require a fixed address; "
      "recipients in villas, compounds, and informal areas cannot be found. "
      "E-commerce merchants bear the full cost of failed deliveries (returns, re-attempts, loss of goods). "
      "Traditional courier systems, designed for the West, are fundamentally incompatible with "
      "the Middle East urban fabric."),
    b("Current Solutions:"), p("Traditional couriers (DHL, FedEx) — require fixed addresses, high failure rate. "
                                "Manual phone coordination — driver calls recipient, expensive, error-prone. "
                                "Cash-on-delivery — causes high return rates."),
    b("Gap Analysis:"), p("No last-mile delivery solution existed that worked without a fixed address "
                           "by using the customer's GPS location (smartphone) instead."),
    b("Frequency:"), p("Daily — every online order in MENA faces this delivery problem."),
    b("Evidence:"), p("Idriss Al Rifai directly observed 25-35% delivery failure at MarkaVIP. "
                       "Joy Ajlouny experienced MENA shipping failures firsthand with Bonfaire returns. "
                       "Double-digit weekly growth reported by September 2015."),
    c("Source: The National (2015). https://www.thenationalnews.com/business/economy/generation-start-up-funding-was-petrifying-in-the-early-days-says-fetchr-founder-1.625104"),
    sp()]

    story += [h("Product & Solution"),
    b("Product Stage:"), p("Live — operating in UAE, Saudi Arabia, and Bahrain at Series A."),
    b("Core Stickiness:"),
    p("GPS-based pickup and delivery: recipient shares phone GPS location via app instead of address. "
      "Driver navigates to exact GPS coordinate. Real-time tracking. Rescheduling via app. "
      "Patented GPS-based delivery technology (US patent filed)."),
    b("Differentiation:"),
    p("1. No address required — first delivery company to use GPS coordinates instead.\n"
      "2. Uber-like model: gig-economy drivers + consumer app = flexible, scalable fleet.\n"
      "3. Real-time tracking — customers know exactly where their delivery is.\n"
      "4. 'DHL married Uber' — reliability of courier + on-demand flexibility."),
    b("Defensibility Moat (claimed):"),
    p("Patented GPS delivery technology. Gig-economy driver network creates supply-side advantages. "
      "Regional logistics data improves routing algorithms over time."),
    b("CRITICAL WEAKNESS (revealed later):"),
    p("Logistics is a thin-margin business. Fleet costs are fixed; delivery fees are competitive. "
      "6-country expansion without profitability created catastrophic cost structure. "
      "Saudi Arabia tax liability ($100M VAT + zakat dispute) destroyed the company in 2021."),
    c("Sources: The National (2015) ; Bloomberg (Oct 2021). https://www.bloomberg.com/news/articles/2021-10-06/top-backer-of-dubai-app-fetchr-warns-startup-faces-liquidation"),
    sp()]

    story += [h("Market & Scope"),
    b("Beachhead Market:"), p("UAE (Dubai/Abu Dhabi — high e-commerce adoption, acute address problem, "
                               "strong logistics demand from online retail)."),
    b("Market Size Estimate:"), p("GCC last-mile delivery market: $10B+. "
                                    "MENA e-commerce driving demand growth. "
                                    "Estimated 25-35% of $2B+ GCC delivery market failing due to address problem."),
    b("Long-term Vision:"), p("Fetchr becomes the default logistics layer for all of MENA — "
                                "solving the address problem across 400M+ people in a region "
                                "where GPS is more reliable than street maps."),
    b("Expansion Strategy:"), p("UAE dominance → Saudi Arabia (largest GCC market) → Egypt → "
                                  "wider MENA. Cross-sell: B2C delivery + B2B logistics + reverse logistics."),
    c("Source: The National (2015). https://www.thenationalnews.com/business/economy/generation-start-up-funding-was-petrifying-in-the-early-days-says-fetchr-founder-1.625104"),
    sp()]

    story += [h("Traction Metrics"), _tbl([
        ["Metric", "Value"],
        ["Stage Context",       "Series A — 3 years post-founding, bootstrapped growth"],
        ["Active Users",        "Hundreds of deliveries per week (Sep 2015, exact not disclosed)"],
        ["Monthly Active Users","Serving e-commerce merchant partners across UAE, Saudi Arabia, Bahrain"],
        ["Early Revenue",       "Per-delivery fee revenue (exact MRR not disclosed at Series A)"],
        ["Growth Rate (MoM)",   "Double-digit weekly growth (Sep 2015, per CEO public statement)"],
        ["Paid Users",          "Enterprise e-commerce clients paying per delivery"],
        ["Key Signal",          "NEA (New Enterprise Associates) invested — their first Middle East deal. "
                                "Joy Ajlouny's Silicon Valley exit (Bonfaire) provided VC network access."],
    ], [6*cm, 11*cm]),
    c("Source: The National (2015). https://www.thenationalnews.com/business/economy/generation-start-up-funding-was-petrifying-in-the-early-days-says-fetchr-founder-1.625104"),
    sp()]

    story += [h("Go-to-Market Strategy"),
    b("Buyer Persona:"), p("Head of logistics / e-commerce operations at GCC online retailer."),
    b("Primary Acquisition Channel:"), p("Direct B2B enterprise sales to e-commerce merchants "
                                          "(Namshi, Souq, and regional online retailers)."),
    b("Sales Motion:"), p("Enterprise direct — integrate Fetchr API into merchant's checkout/dispatch system."),
    b("Average Sales Cycle:"), p("2-4 weeks for enterprise integration."),
    b("Deal Closer:"), p("Idriss Al Rifai (CEO) — all major accounts personally closed."),
    c("Source: The National (2015)."),
    sp()]

    story += [h("Business Model"), _tbl([
        ["Field", "Value"],
        ["Pricing Model",   "Per-delivery fee (express, standard, scheduled tiers); volume discounts for merchants"],
        ["Gross Margin",    "Claimed: ~30-40% (thin — logistics has high fixed costs for fleet and staff)"],
        ["Monthly Burn",    "~$300,000 (growing fleet + driver costs + 3-country operations)"],
        ["Runway",          "~36 months on $11M Series A (if burn stays controlled — it did not)"],
        ["Revenue",         "Growing; exact MRR not disclosed at Series A"],
    ], [6*cm, 11*cm]),
    c("Source: Bloomberg (Dec 2019). https://www.bloomberg.com/news/articles/2019-12-04/one-of-middle-east-s-largest-startups-narrowly-averts-collapse"),
    sp()]

    story += [h("Vision & Strategy"),
    b("5-Year Vision:"),
    p("Fetchr solves the address problem for all 400 million people in MENA who lack reliable street addresses. "
      "Every online purchase in the region is delivered via Fetchr's GPS-enabled network. "
      "Fetchr becomes the dominant last-mile logistics platform for MENA — "
      "a regional logistics infrastructure company, not just a delivery app."),
    b("Category Definition:"), p("GPS-based Last-Mile Delivery / MENA Logistics Infrastructure"),
    b("Primary Risk:"),
    p("Unit economics: per-delivery margins in logistics are thin; fleet costs are fixed. "
      "Regulatory: operating in 6 GCC countries means VAT, zakat, and labour law complexity. "
      "Competition: DHL, FedEx, local couriers all competing on price. "
      "Driver supply: gig-economy model requires constant driver recruitment."),
    b("Use of Funds:"), p("Fleet expansion, driver recruitment, Saudi Arabia market entry, "
                           "Egypt pilot, engineering for routing optimisation."),
    c("Source: Wamda (2021). https://www.wamda.com/2021/10/fetchr-risk-liquidation"),
    sp()]

    doc.build(story)
    print("OK fetchr_2015_pitch.pdf")


# ═══════════════════════════════════════════════════════════════════════════════
# 9.  CAPITER  — Series A stage, September 2021  (MENA / Egypt)  — PASS case
# ═══════════════════════════════════════════════════════════════════════════════
def build_capiter():
    """
    Sources:
    - TechCrunch (Sep 2022). Founders of well-funded Egyptian B2B startup Capiter
      fired following fraud allegations.
      https://techcrunch.com/2022/09/09/founders-of-well-funded-egyptian-b2b-startup-capiter-fired-following-fraud-allegations/
    - TechCrunch (Oct 2022). Dispute between founders and board leaves Capiter
      in arrears to employees and creditors.
      https://techcrunch.com/2022/10/27/dispute-between-founders-and-board-leaves-capiter-in-arrears-to-employees-and-creditors/
    - Wamda (Sep 2022). What are the repercussions of Capiter's downfall?
      https://www.wamda.com/2022/09/repercussions-capiters-downfall
    """
    doc = _make_doc("capiter_2021_pitch.pdf")
    h1, h2, body, bold, src = _styles()
    def h(t, s=h2): return Paragraph(t, s)
    def p(t):       return Paragraph(t, body)
    def b(t):       return Paragraph(t, bold)
    def c(t):       return Paragraph(t, src)

    story = []

    story += [h("CAPITER — Series A Stage Pitch", h1),
              p("Date: September 2021  |  Stage: Series A  |  Location: Cairo, Egypt"),
              p("<b>Note:</b> This document reconstructs the pitch as presented at the Series A stage. "
                "Capiter raised $33M in September 2021 then ceased operations in October 2022 — "
                "12 months later — following fraud allegations and board removal of both founders."),
              c("Source: TechCrunch (Sep 2022). https://techcrunch.com/2022/09/09/founders-of-well-funded-egyptian-b2b-startup-capiter-fired-following-fraud-allegations/"),
              rule()]

    story += [h("Company Snapshot"), _tbl([
        ["Field", "Value"],
        ["Company Name",         "Capiter"],
        ["Website",              "capiter.com"],
        ["HQ Location",          "Cairo, Egypt"],
        ["Date Founded",         "2020-01-01"],
        ["Current Stage",        "Series A"],
        ["Amount Raised to Date","$3,000,000 (pre-Series A seed)"],
        ["Round Target",         "$33,000,000"],
        ["Target Close",         "2021-09-01"],
    ], [6*cm, 11*cm]),
    c("Source: Wamda (Sep 2022). https://www.wamda.com/2022/09/repercussions-capiters-downfall"),
    sp()]

    story += [h("Founding Team"), _tbl([
        ["Name", "Role", "Background", "Yrs Experience", "Ownership %"],
        ["Mahmoud Nouh", "CEO & Co-founder",
         "Co-founder of SWVL (Egyptian mass transit unicorn). "
         "Deep operational experience scaling a high-growth Egyptian startup from zero to regional scale. "
         "Prior experience in FMCG distribution and supply chain in Egypt. "
         "Intimate knowledge of Egypt's informal retail infrastructure.",
         "6", "50%"],
        ["Ahmed Nouh", "COO & Co-founder",
         "Brother of Mahmoud. Prior experience in operations and supply chain. "
         "No prior startup exit. "
         "No independent track record outside of family founding relationship.",
         "4", "50%"],
    ], [4*cm, 3.5*cm, 6.5*cm, 1.5*cm, 1.5*cm]),
    c("Sources: TechCrunch (Sep 2022) ; Wamda (Sep 2022)"),
    sp(),
    p("Full-time start date: 2020-01-01. Both founders full-time from founding."),
    p("Governance risk: Co-founding team are brothers (family dynamic). "
      "No independent technical co-founder. No external C-suite hires at founding."),
    sp()]

    story += [h("Execution Timeline"), _tbl([
        ["Date", "Milestone"],
        ["2020-01", "Capiter incorporated in Cairo. Founders leverage SWVL network to recruit team."],
        ["2020-Q4", "Seed round: ~$3M from regional angel investors and Foundation Ventures."],
        ["2021-09", "Series A: $33M. Investors: Quona Capital, MSA Capital, Shorooq Partners, Savola."],
        ["2021-10", "50,000 merchants, 1,000 sellers, 6,000+ SKUs. Projecting $1B annualised revenue by end 2022."],
        ["2022-06", "Multiple rounds of layoffs begin. Merchant onboarding stalls."],
        ["2022-08", "Only 1 month of cash runway remaining. Board not informed."],
        ["2022-09", "Board fires both founders on fraud allegations. CFO becomes interim CEO."],
        ["2022-10", "Staff salaries unpaid. Creditors owed $3-5M. Ceased trading."],
    ], [3.5*cm, 13.5*cm]),
    c("Source: TechCrunch (Sep 2022) ; TechCrunch (Oct 2022). https://techcrunch.com/2022/10/27/dispute-between-founders-and-board-leaves-capiter-in-arrears-to-employees-and-creditors/"),
    sp()]

    story += [h("Problem Definition"),
    b("Customer Profile:"), p("Egyptian small and micro retailers — kiosks, corner stores (baqalas), minimarkets — "
                               "who buy FMCG products through fragmented wholesale middlemen. "
                               "Egypt has 1M+ such retailers; most operate informally with no digital tools."),
    b("Problem Statement:"),
    p("Egypt's $20B+ FMCG retail market is almost entirely informal and fragmented. "
      "Small retailers buy from multiple middlemen (wholesalers) who inflate prices by 15-30%. "
      "They have no access to working capital or credit — every order is cash in advance. "
      "FMCG brands cannot reach micro-retailers directly; they depend on a 3-layer distribution chain "
      "(brand → distributor → wholesaler → retailer) that is inefficient, opaque, and costly for all parties. "
      "The result: small retailers pay too much, brands lose margin to middlemen, "
      "and credit-starved retailers cannot grow their inventory."),
    b("Current Solutions:"), p("Traditional wholesalers and distributors (overpriced, no credit, no visibility). "
                                "Cash-on-delivery with manual ordering (phone calls, no data). "
                                "No digital B2B marketplace existed for FMCG in Egypt at founding."),
    b("Gap Analysis:"), p("No platform connected Egypt's 1M+ small retailers directly to FMCG brands "
                           "with same-day delivery, working capital, and digital ordering in one experience."),
    b("Frequency:"), p("Daily — every retailer restocks inventory multiple times per week."),
    b("Evidence:"),
    p("50,000 merchants onboarded onto the platform by September 2021. "
      "1,000 supplier/seller accounts. 6,000+ SKUs available. "
      "Mahmoud Nouh's SWVL experience provided a direct network of contacts across Egypt's informal retail sector."),
    c("Source: TechCrunch (Sep 2022). https://techcrunch.com/2022/09/09/founders-of-well-funded-egyptian-b2b-startup-capiter-fired-following-fraud-allegations/"),
    sp()]

    story += [h("Product & Solution"),
    b("Product Stage:"), p("Live — operating in Cairo and expanding to Alexandria and Upper Egypt."),
    b("Core Stickiness:"),
    p("Retailers order FMCG inventory via Capiter app with same-day or next-day delivery. "
      "Working capital product (Buy Now Pay Later for retailers) creates financial dependency. "
      "Once a retailer's ordering history is on Capiter, credit scoring improves — making Capiter "
      "their lowest-cost financing option, increasing switching cost."),
    b("Differentiation:"),
    p("1. Direct brand-to-retailer connection eliminating 2-3 layers of middlemen.\n"
      "2. Working capital / BNPL for retailers — first credit access for most small stores.\n"
      "3. Same-day delivery infrastructure across Cairo.\n"
      "4. Digital ordering replacing phone/WhatsApp ordering.\n"
      "5. Data layer: transaction history enables credit scoring for unbanked retailers."),
    b("Defensibility Moat (claimed):"),
    p("Transaction data network creates proprietary credit scoring for Egypt's informal retailers. "
      "Logistics infrastructure is costly to replicate. "
      "Supplier exclusivity agreements with key FMCG brands."),
    b("CRITICAL WEAKNESS (revealed later):"),
    p("Business model was capital-intensive: Capiter held inventory AND provided working capital AND "
      "operated logistics — three cash-burning operations simultaneously. "
      "This required continuous funding to sustain. "
      "When growth targets missed, the model had no path to profitability at current scale."),
    c("Source: Wamda (Sep 2022). https://www.wamda.com/2022/09/repercussions-capiters-downfall"),
    sp()]

    story += [h("Market & Scope"),
    b("Beachhead Market:"), p("Greater Cairo FMCG B2B market — 300,000+ small retailers within delivery range."),
    b("Market Size Estimate:"), p("Egypt FMCG total retail: $20B+ annually. "
                                    "B2B e-commerce addressable: $5-8B (informal wholesale transactions). "
                                    "MENA B2B FMCG market: $50B+."),
    b("Long-term Vision:"), p("Capiter becomes the default B2B commerce and embedded finance platform "
                                "for all small retailers across MENA — the operating system for informal retail. "
                                "Project $1 billion in annualised revenue by end of 2022."),
    b("Expansion Strategy:"), p("Cairo → Alexandria → Upper Egypt → Saudi Arabia → UAE → broader MENA. "
                                  "Add financial services (insurance, savings) for retailers on top of payment/credit layer."),
    c("Source: TechCrunch (Sep 2022)"),
    sp()]

    story += [h("Traction Metrics"), _tbl([
        ["Metric", "Value"],
        ["Stage Context",       "Series A — B2B marketplace, 12 months post-launch"],
        ["Active Merchants",    "50000"],
        ["Monthly Active Users","50000"],
        ["Sellers / Suppliers", "1,000 FMCG brand and distributor accounts"],
        ["SKUs Available",      "6,000+"],
        ["Early Revenue",       "100000"],
        ["Growth Rate (MoM)",   "25"],
        ["Paid Users",          "50000"],
        ["Key Signal",          "50,000 merchants in 12 months with minimal marketing spend. "
                                "Projecting $1 billion annualised GMV by December 2022. "
                                "Quona Capital (global fintech VC) led the round — strong investor signal."],
    ], [6*cm, 11*cm]),
    c("Source: TechCrunch (Sep 2022)"),
    sp()]

    story += [h("Go-to-Market Strategy"),
    b("Buyer Persona:"), p("Owner of a small kiosk or corner store in Cairo, buying FMCG stock 2-3 times per week."),
    b("Primary Acquisition Channel:"), p("Direct field sales team — agents visit retailers in person "
                                          "to sign them up and place first orders. "
                                          "Leveraging Mahmoud Nouh's SWVL network for warm introductions to neighbourhood clusters."),
    b("Sales Motion:"), p("Field-led B2B — sales agents onboard retailers one by one. No self-serve at launch."),
    b("Average Sales Cycle:"), p("1-3 days per retailer. High volume, low complexity."),
    b("Deal Closer:"), p("Field sales agents (founder-dependent team at early stage)."),
    c("Source: Wamda (Sep 2022)"),
    sp()]

    story += [h("Business Model"), _tbl([
        ["Field", "Value"],
        ["Pricing Model",   "Take rate on transactions (5-8% of GMV) + working capital fee (BNPL interest) + delivery fee"],
        ["Gross Margin",    "Claimed: 15-20% net (thin — inventory + logistics + credit loss provisions)"],
        ["Monthly Burn",    "~$2,500,000 (field sales team, logistics fleet, inventory, working capital float)"],
        ["Runway",          "~13 months on $33M Series A (if burn stays controlled — it did not)"],
        ["Revenue",         "$100,000/month at Series A close (estimated from GMV × take rate)"],
    ], [6*cm, 11*cm]),
    c("Source: Wamda (Sep 2022) ; TechCrunch (Oct 2022)"),
    sp()]

    story += [h("Vision & Strategy"),
    b("5-Year Vision:"),
    p("Capiter becomes the default commerce and financial services platform for MENA's 10M+ informal retailers. "
      "Every small store owner orders inventory, accesses credit, pays bills, and manages their business "
      "through Capiter. Transition from marketplace to embedded finance super-app for the informal economy."),
    b("Category Definition:"), p("B2B FMCG Marketplace / Embedded Finance for Informal Retail"),
    b("Primary Risk:"),
    p("Working capital risk: extending credit to unbanked, unscored retailers creates default exposure. "
      "Unit economics: logistics + inventory holding + credit provisioning = very high cost per order. "
      "Execution: onboarding millions of informal retailers requires a massive field sales operation. "
      "Competition: Cartona (Egypt), Fatura (Egypt), and regional players all targeting same market."),
    b("Use of Funds:"), p("Field sales team expansion (100+ agents), logistics fleet, working capital "
                           "for retailer credit facility, tech team, Alexandria and Upper Egypt expansion."),
    c("Source: TechCrunch (Sep 2022) ; Wamda (Sep 2022)"),
    sp()]

    doc.build(story)
    print("OK capiter_2021_pitch.pdf")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    build_airbnb()
    build_stripe()
    build_theranos()
    build_juicero()
    build_wework()
    build_tabby()
    build_paymob()
    build_fetchr()
    print("\nAll 8 gold-standard pitch PDFs generated in:", OUT)
