"""
Generate a realistic YouTube (2005 Seed) pitch document as a PDF.

Data sourced from Sequoia's leaked investment memo (Roelof Botha, Sep 2005),
publicly released via the Viacom v. YouTube lawsuit.

Run from project root:
    python app/graph/pdf_extractor/generate_youtube_pitch.py
Output:
    app/graph/pdf_extractor/youtube_2005_pitch.pdf
"""

from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.enums import TA_CENTER

OUTPUT = Path(__file__).parent / "youtube_2005_pitch.pdf"


def build():
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=18, spaceAfter=6)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=13, spaceBefore=14, spaceAfter=4)
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=10, leading=14, spaceAfter=4)
    bold = ParagraphStyle("bold", parent=body, fontName="Helvetica-Bold")

    def h(text, style=h2): return Paragraph(text, style)
    def p(text): return Paragraph(text, body)
    def b(text): return Paragraph(text, bold)
    def sp(n=6): return Spacer(1, n)
    def rule(): return HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey, spaceAfter=6)

    def table(data, col_widths):
        t = Table(data, colWidths=col_widths)
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return t

    story = []

    # ── Cover ──────────────────────────────────────────────────────────────────
    story += [
        sp(20),
        h("YouTube", ParagraphStyle("cover", parent=h1, fontSize=28, alignment=TA_CENTER)),
        p("<para align='center'><i>Seed Round Pitch Document — September 2005</i></para>"),
        p("<para align='center'>Confidential — For Investor Use Only</para>"),
        sp(40),
        rule(),
    ]

    # ── Company Snapshot ───────────────────────────────────────────────────────
    story += [h("Company Snapshot")]
    story += [table([
        ["Company Name", "YouTube"],
        ["Website", "www.youtube.com"],
        ["Headquarters", "San Mateo, California, USA"],
        ["Date Founded", "2005-02-01"],
        ["Current Stage", "Seed"],
        ["Amount Raised to Date", "USD 0 (pre-seed, bootstrapped)"],
        ["Current Round Target", "USD 1,000,000 (Seed) + USD 4,000,000 (Series A on milestones)"],
        ["Target Close Date", "2005-10-01"],
    ], [5 * cm, 11 * cm]), sp()]

    # ── Founders & Team ────────────────────────────────────────────────────────
    story += [rule(), h("Founders & Team")]
    story += [
        b("Steve Chen — Co-founder & CTO"),
        p("Former PayPal engineer (6 years). Led PayPal China expansion, XML API infrastructure, and "
          "Shopping Cart product. Expert in high-scale backend systems. "
          "8 years of direct experience in consumer internet engineering. Ownership: 34%."),
        sp(),
        b("Chad Hurley — Co-founder & Head of Design & Product"),
        p("PayPal's first designer. Responsible for PayPal's original consumer interface and auction "
          "integration features. 10 years of direct experience in product design and user experience. "
          "Ownership: 33%."),
        sp(),
        b("Jawed Karim — Co-founder & Engineer"),
        p("Stanford Computer Science graduate student. Former PayPal anti-fraud systems architect. "
          "7 years of direct experience in machine learning and fraud detection systems. Ownership: 33%."),
        sp(),
        p("Two additional former PayPal engineers joining full-time by October 2005. "
          "CEO search in progress; target hire within 90 days."),
        sp(4),
        b("Execution Timeline"),
        table([
            ["Date", "Milestone"],
            ["2005-02-01", "Company incorporated; team begins full-time development."],
            ["2005-04-23", "First public beta launched at youtube.com."],
            ["2005-06-11", "Official public launch."],
            ["2005-07-15", "Surpassed 15,000 total uploaded videos; 100,000 daily video views."],
            ["2005-08-01", "Overtook all existing video-sharing competitors in daily traffic."],
            ["2005-09-02", "140% compounded monthly page-view growth over prior 3 months."],
        ], [3.5 * cm, 12.5 * cm]),
        sp(),
    ]

    # ── Problem ────────────────────────────────────────────────────────────────
    story += [rule(), h("Problem Definition")]
    story += [
        b("Customer Profile: Content creators and consumers — individuals aged 18–35 with broadband access."),
        p("Sharing a personal video online in 2005 requires technical knowledge: encode to the right codec, "
          "find a web host, embed a player, and ensure the recipient's browser supports it. "
          "Most people give up. Meanwhile, video cameras are now built into every phone and digital camera, "
          "creating massive supply of personal video with no accessible distribution channel."),
        sp(),
        b("Current Solutions & Gaps:"),
        p("iFilm and eBaum's World require editorial approval — not self-serve. "
          "Google Video has days of lag and requires manual review. "
          "Dailymotion uses QuickTime encoding — only 60% of browsers can play it. "
          "Vimeo is CollegeHumor-owned with no search functionality. "
          "No solution lets anyone upload, share, and instantly stream a video in under two minutes."),
        sp(),
        p("Customer interviews conducted: 120+ informal user sessions during beta. "
          "Frequency of need: daily. 1 billion camera-phones shipped worldwide by 2005."),
    ]

    # ── Product ────────────────────────────────────────────────────────────────
    story += [rule(), h("Product & Solution")]
    story += [
        b("Product Stage: Live Product (publicly launched June 11, 2005)"),
        p("Demo: www.youtube.com"),
        p("YouTube converts every uploaded video to Flash format, which runs natively in 98% of web browsers "
          "with no plugin download required. Upload takes under two minutes. Videos stream instantly. "
          "Users can embed videos on any external website via a single line of HTML."),
        sp(),
        b("Core Stickiness:"),
        p("Community features — comments, ratings, channel subscriptions — create social hooks. "
          "The embed feature turns every YouTube video into a viral distribution unit: one viral video "
          "drives thousands of new registered users from external blogs and forums."),
        sp(),
        b("Differentiation:"),
        p("Flash encoding vs. QuickTime (competitors): 98% vs. 60% browser compatibility. "
          "No editorial approval gate — anyone can publish instantly. "
          "Search and browse by tag, user, and category. "
          "Embed code allows distribution across the entire web, not just youtube.com."),
        sp(),
        b("Defensibility Moat:"),
        p("Network effects: more videos attract more viewers; more viewers attract more uploaders. "
          "First-mover advantage in Flash-encoded UGC video. "
          "Community data (views, ratings, comments) creates a self-improving content quality signal."),
    ]

    # ── Market ─────────────────────────────────────────────────────────────────
    story += [rule(), h("Market & Scope")]
    story += [
        b("Beachhead Market:"),
        p("18–35 year old broadband users in the United States who own a digital camera or camera-phone "
          "and participate in online communities (MySpace, blogs, forums). Estimated 40 million users."),
        sp(),
        b("Market Size Estimate: USD 1,500,000,000 (online video advertising + premium content, USA 2009E)."),
        p("User-generated video is the natural evolution of text blogging (2000), photo sharing/Flickr (2002), "
          "and podcasting (2004). Each wave was larger than the last. US broadband penetration reached 50% in 2005. "
          "eMarketer projects US online video advertising to reach $640M by 2007 and $1.5B by 2009."),
        sp(),
        b("Long-Term Vision:"),
        p("YouTube becomes the default video layer of the internet — the place where any video, "
          "from a home movie to a news clip, is found, shared, and discussed. "
          "Television networks, movie studios, and brands distribute content directly through YouTube channels, "
          "monetized through targeted video advertising."),
        sp(),
        b("Expansion Strategy:"),
        p("Consumer UGC first → Partner channels for media companies → "
          "Self-serve advertising platform → International expansion → "
          "B2B syndication API for third-party websites."),
    ]

    # ── Traction ───────────────────────────────────────────────────────────────
    story += [rule(), h("Traction Metrics")]
    story += [
        p("Stage context: Seed (3 months post-public launch)."),
        table([
            ["Metric", "Value", "Note"],
            ["Daily video views", "100,000", "As of August 2005"],
            ["Total videos uploaded", "15,000", "As of August 2005"],
            ["Monthly page-view growth (CMGR)", "140%", "Compounded over prior 3 months"],
            ["Time to market leadership", "2.5 months", "Overtook all competitors"],
            ["Early revenue", "USD 0", "Pre-revenue; monetization in design"],
            ["Growth rate", "140", "Monthly % CMGR"],
        ], [5.5 * cm, 4 * cm, 6.5 * cm]),
        sp(),
        p("Partnerships / LOIs: Discussions ongoing with eBay (auction video), "
          "real estate platforms, and three major record labels for music video distribution."),
        p("Active users monthly: 80,000 (estimated from daily view data and session patterns)."),
    ]

    # ── GTM Strategy ──────────────────────────────────────────────────────────
    story += [rule(), h("Go-to-Market Strategy")]
    story += [
        table([
            ["GTM Element", "Detail"],
            ["Primary Acquisition Channel", "Viral / embed sharing (MySpace, blogs, forums)"],
            ["Sales Motion", "Self-serve"],
            ["Buyer vs End User", "Same person — individual content creator or consumer"],
            ["Average Sales Cycle", "Instant — zero-friction self-sign-up, no sales rep needed"],
            ["Deal Closer", "Product (viral loop)"],
            ["Distribution Mechanism",
             "Embed code snippet: any user can paste a YouTube video onto any webpage. "
             "Each embedded video is a free ad driving new registrations. "
             "MySpace integration in 2005 provided the initial viral catalyst."],
        ], [5 * cm, 11 * cm]),
        sp(),
        p("Growth flywheel: more content → more embeds on external sites → more new users → "
          "more uploads → more content. Self-reinforcing loop with no paid acquisition required at seed stage."),
    ]

    # ── Business Model ─────────────────────────────────────────────────────────
    story += [rule(), h("Business Model & Financials")]
    story += [
        table([
            ["Revenue Stream", "Description", "Year 2 Projection"],
            ["Video advertising (CPM)", "Video ads as related content; $5–$30 CPM", "$6M–$22M"],
            ["Interactive in-player ads", "Flash overlay ads within the video player", "Included above"],
            ["Pre-roll video ads", "15-second pre-roll before premium content", "Included above"],
            ["Premium membership", "Downloads, HD quality, editing tools — $9.99/month", "$2M"],
            ["Paid promotional distribution", "Brands pay for promoted placement", "$1M"],
        ], [4.5 * cm, 7 * cm, 4.5 * cm]),
        sp(),
        p("Financial scenarios (10M–30M daily video views):"),
        p("  Conservative: USD 6,000,000 annual revenue"),
        p("  Base case:    USD 22,000,000 annual revenue"),
        p("  Optimistic:  USD 55,000,000 annual revenue"),
        sp(),
        p("Gross margin: 70%+ (software/advertising; bandwidth cost declines with CDN scale)."),
        p("Average price per customer (premium): USD 119.88 per year."),
        p("Monthly burn: USD 80,000 (3 engineers + infrastructure). Runway months: 12."),
    ]

    # ── Vision & Strategy ──────────────────────────────────────────────────────
    story += [rule(), h("Vision & Strategy")]
    story += [
        b("Five-Year Vision:"),
        p("YouTube becomes the default video layer of the internet — every video clip, home movie, "
          "news event, and brand advertisement is hosted, shared, and monetized through YouTube. "
          "Television networks syndicate content directly. Advertisers buy targeted video placements "
          "the same way they buy Google AdWords. YouTube is to video what Google is to text search."),
        sp(),
        b("Category Definition: User-Generated Video (UGV) Platform"),
        sp(),
        b("Primary Risk:"),
        p("Copyright infringement: users are already uploading copyrighted music videos and TV clips. "
          "A DMCA safe-harbor strategy and proactive content ID system must be built. "
          "Revenue model uncertainty: can video advertising scale without hurting user experience? "
          "Scalability: infrastructure must handle 100x growth without proportional cost increase."),
    ]

    # ── Funding Ask ────────────────────────────────────────────────────────────
    story += [rule(), h("Funding Ask")]
    story += [
        table([
            ["Round", "Amount", "Sequoia Ownership Post", "Series A Milestones"],
            ["Seed", "USD 1,000,000", "~15%", "N/A — immediate close"],
            ["Series A", "USD 4,000,000", "~30% total",
             "1M daily views | 5 paying advertisers ($5K+) | VP BizDev hired | business plan complete"],
        ], [2.5 * cm, 3.5 * cm, 4 * cm, 6 * cm]),
        sp(),
        p("Use of funds: Infrastructure scaling (CDN, storage), engineering hires (2), "
          "legal (DMCA/copyright counsel), and business development."),
        sp(20),
        rule(),
        p("<para align='center'><i>Data sourced from: Sequoia Capital investment memo by Roelof Botha, "
          "September 2, 2005 — released publicly via Viacom v. YouTube (2010) court proceedings.</i></para>"),
    ]

    doc.build(story)
    print(f"PDF written to: {OUTPUT}")


if __name__ == "__main__":
    build()
