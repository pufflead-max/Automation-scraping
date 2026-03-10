"""
Buyer Intent Detection Module (ML-powered)
Uses Scikit-Learn (TF-IDF + Logistic Regression) for high-speed CPU classification.
This model is trained on synthetic but realistic samples of service requests vs advertisements.
"""

import os
import re
import joblib
import numpy as np
from typing import Optional, List, Dict, Any
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

class BuyerMLDetector:
    """
    ML Classifier for Buyer Intent.
    Trained to distinguish between people LOOKING for services and people OFFERING services.
    """
    
    MODEL_PATH = os.path.join(os.path.dirname(__file__), "buyer_model.joblib")

    # ── TRAINING DATA ──────────────────────────────────────────────────────────
    # This dataset represents common phrasing on Craigslist/Facebook.
    TRAINING_DATA = [
        # =========================================================
        # BUYERS — Label: 1  (Genuine leads seeking contractor help)
        # =========================================================

        # --- Landscaping ---
        ("I need help with leaf removal this weekend.", 1),
        ("ISO someone to mow my yard weekly.", 1),
        ("In search of a reliable landscaping company for spring.", 1),
        ("Looking for recommendations for leaf service.", 1),
        ("I want to hire someone for yard work.", 1),
        ("Who do you guys use for lawn care?", 1),
        ("Can anyone recommend a landscaper for a full yard cleanup?", 1),
        ("Need someone to trim my hedges and edge the lawn.", 1),
        ("Looking for a crew to do a spring cleanup at my property.", 1),
        ("Anyone know a good landscaper for weekly maintenance?", 1),
        ("Need sod installation done by end of month.", 1),
        ("Who can I hire to mulch my flower beds?", 1),
        ("Looking for someone to aerate and overseed my lawn.", 1),
        ("Need a landscaping quote for a backyard renovation.", 1),
        ("Does anyone have a contact for tree trimming near me?", 1),
        ("ISO a landscaper to handle my HOA-required lawn upkeep.", 1),
        ("Looking to get my backyard leveled and graded.", 1),
        ("Anyone recommend a lawn service that does fall cleanup?", 1),
        ("Need help removing a dead tree from my yard.", 1),
        ("Seeking a landscaper for a complete front yard makeover.", 1),

        # --- Painting ---
        ("Can anyone recommend a good painter for my living room?", 1),
        ("How much to paint a house in Brooklyn?", 1),
        ("Looking for a painter to do my exterior this spring.", 1),
        ("Need an interior painter for 3 bedrooms ASAP.", 1),
        ("ISO a painter who can match existing wall color.", 1),
        ("Looking for someone to paint my fence and deck.", 1),
        ("Who can I hire to repaint my kitchen cabinets?", 1),
        ("Need a quote for painting the entire first floor.", 1),
        ("Anyone have a reliable painter they'd recommend?", 1),
        ("Seeking a painter to touch up after some drywall repairs.", 1),
        ("Need a professional painter for a commercial space.", 1),
        ("Who does affordable painting work in this area?", 1),
        ("Looking for a painter with experience on older homes.", 1),
        ("Need exterior painting done before winter.", 1),
        ("ISO a painter for a small bathroom refresh.", 1),
        ("Can anyone refer me to a painter who also does staining?", 1),
        ("Need someone to paint my garage interior.", 1),
        ("Who painted your house? Looking for referrals!", 1),
        ("Looking for a painter available mid-April.", 1),
        ("Need painting done in a rental unit, must be quick.", 1),

        # --- Asphalt Paving ---
        ("Need a quote for repaving my driveway.", 1),
        ("Who can I hire to patch potholes in my parking lot?", 1),
        ("Looking for an asphalt company to resurface my driveway.", 1),
        ("ISO paving contractor for a commercial lot.", 1),
        ("My driveway is cracking badly, need a paving quote.", 1),
        ("Anyone know a good asphalt paving company locally?", 1),
        ("Need sealcoating done on my driveway this season.", 1),
        ("Looking to get a new asphalt driveway installed.", 1),
        ("Who does asphalt work around here? Need referrals.", 1),
        ("Need a paving contractor for a small parking area.", 1),
        ("ISO someone to do crack filling and sealcoating.", 1),
        ("My HOA needs the parking lot repaved, who to call?", 1),
        ("Looking for a paving crew for a 2-car driveway.", 1),
        ("Need asphalt repair before the rainy season.", 1),
        ("Anyone recommend a paving company that's not overpriced?", 1),

        # --- Carpentry ---
        ("ISO referral for a good mason.", 1),
        ("Looking for a carpenter to build custom shelving.", 1),
        ("Need someone to repair my deck boards.", 1),
        ("Who can build a custom mudroom bench and cubbies?", 1),
        ("ISO a carpenter for trim and molding installation.", 1),
        ("Looking for a woodworker to build a built-in bookcase.", 1),
        ("Need a carpenter to frame a new closet.", 1),
        ("Who does custom cabinet work in this area?", 1),
        
        # --- Kitchen & Bath ---
        ("Looking for a contractor to remodel my master bathroom.", 1),
        ("ISO someone to do a full kitchen renovation.", 1),
        ("Need a quote for new countertops and a backsplash.", 1),
        ("Can anyone recommend a good bathroom remodeler?", 1),
        ("Seeking a specialist for a kitchen cabinet refacing project.", 1),
        ("Looking to update my small guest bath, any referrals?", 1),
        ("Who do you guys use for kitchen and bath design/build?", 1),
        ("Need a professional for a walk-in shower conversion.", 1),
        ("ISO a kitchen contractor who can also do flooring.", 1),
        ("Looking for a high-end bathroom renovation company.", 1),

        # --- Plumbing ---
        ("Who is your go-to plumber for emergency leaks?", 1),
        ("Looking for a plumber to install a new water heater.", 1),
        ("Need someone to snake a clogged drain in my basement.", 1),
        ("ISO a reliable plumber for a kitchen sink replacement.", 1),
        ("My toilet won't stop running, need a plumber today.", 1),
        ("Can anyone recommend a plumber for a sewer line inspection?", 1),
        ("Seeking a plumber to move some pipes for a renovation.", 1),
        ("Need a quote for a new sump pump installation.", 1),
        ("Who do you use for gas line repairs? Looking for a plumber.", 1),
        ("Leaking pipe in my wall, need a plumber ASAP!", 1),

        # --- Electrical ---
        ("Looking for a licensed electrician to add some outlets.", 1),
        ("ISO an electrician to install a ceiling fan and light fixture.", 1),
        ("Need someone to upgrade my electrical panel to 200 amps.", 1),
        ("Can anyone recommend a good residential electrician?", 1),
        ("Seeking an electrician for a backup generator installation.", 1),
        ("Need an electrician to troubleshoot some flickering lights.", 1),
        ("Who do you use for outdoor landscape lighting? Need an electrician.", 1),
        ("Looking to get an EV charger installed in my garage.", 1),
        ("ISO an electrician for a full house rewire project.", 1),
        ("Need a quote for recessed lighting in my living room.", 1),
        ("Need someone to replace rotted wood on my porch.", 1),
        ("Looking for a finish carpenter for a home renovation.", 1),
        ("ISO a carpenter experienced in hardwood stair treads.", 1),
        ("Need a carpenter to install crown molding throughout my home.", 1),
        ("Who can build a custom pergola in my backyard?", 1),
        ("Looking for a carpenter to repair my garage door frame.", 1),
        ("Need a handyman or carpenter to fix squeaky floors.", 1),

        # --- Fence Installation & Repair ---
        ("Does anyone know a professional to fix a broken fence?", 1),
        ("Need a fence contractor for a 200-foot privacy fence.", 1),
        ("Looking for someone to replace fence posts after storm damage.", 1),
        ("ISO a fencing company for a wood privacy fence estimate.", 1),
        ("Who installs vinyl fencing around here?", 1),
        ("Need a chain link fence installed around my property.", 1),
        ("Looking for a fence repair company after my neighbor's tree fell.", 1),
        ("ISO a contractor to install a fence gate with a lock.", 1),
        ("Need a quote for a split rail fence for my front yard.", 1),
        ("Who can install an aluminum fence around a pool area?", 1),
        ("My fence was damaged by a car, need repair estimate.", 1),
        ("Looking for a fencing contractor for a commercial property.", 1),
        ("Need decorative fence panels installed along my driveway.", 1),
        ("ISO a fence installer for a dog-friendly backyard.", 1),
        ("Who does cedar fence installation in this neighborhood?", 1),

        # --- Flooring Installation & Repair ---
        ("Anyone recommend a good crew for flooring?", 1),
        ("Seeking a professional for tile installation.", 1),
        ("Need hardwood floors refinished in my living room.", 1),
        ("ISO a flooring contractor for LVP installation.", 1),
        ("Looking for someone to install tile in my bathroom.", 1),
        ("Need carpet removed and replaced with hardwood.", 1),
        ("Who installs engineered hardwood in this area?", 1),
        ("Need a quote to tile my kitchen floor.", 1),
        ("Looking for a flooring company that does laminate.", 1),
        ("ISO a flooring specialist to repair water-damaged subfloor.", 1),
        ("Need stair treads replaced, who should I call?", 1),
        ("Who does epoxy garage floor coating around here?", 1),
        ("Looking for a flooring crew for a full house renovation.", 1),
        ("Need grout resealing and tile repair in my bathroom.", 1),
        ("ISO someone to install heated tile floors in my master bath.", 1),

        # --- Cleaning Services ---
        ("Need someone to deep clean my apartment.", 1),
        ("Looking for a house cleaner once a week.", 1),
        ("ISO a reliable cleaning service for a move-out clean.", 1),
        ("Need post-construction cleaning for a newly renovated home.", 1),
        ("Who offers commercial office cleaning services here?", 1),
        ("Looking for a carpet cleaning company ASAP.", 1),
        ("Need someone to clean my gutters and power wash the siding.", 1),
        ("ISO a cleaning crew for an Airbnb property.", 1),
        ("Need a biweekly house cleaner starting next month.", 1),
        ("Who does window cleaning for a 2-story home?", 1),
        ("Looking for a deep cleaning service before selling my house.", 1),
        ("Need a pressure washing crew for my driveway and patio.", 1),
        ("ISO a maid service that does laundry too.", 1),
        ("Need upholstery and sofa cleaning done this week.", 1),
        ("Who does move-in cleaning services around here?", 1),

        # --- Snow Removal ---
        ("Who can I hire to plow my driveway today?", 1),
        ("Needs help with snow removal today.", 1),
        ("Looking for a snow plow service for this winter.", 1),
        ("ISO a snow removal company for a small commercial lot.", 1),
        ("Need someone to shovel my driveway and walkway after each storm.", 1),
        ("Who does seasonal snow contracts in this area?", 1),
        ("Need ice melt application for my business entrance.", 1),
        ("Looking for a reliable snow removal crew for the season.", 1),

        # --- General / Plumbing / Handyman (as neighbors would post) ---
        ("I need help with leaf removal this weekend.", 1),
        ("Looking for a reliable plumber in my area.", 1),
        ("I am seeking a quote for a kitchen remodel.", 1),
        ("Looking for a local handyman for small repairs.", 1),
        ("Available today to fix a leaking pipe?", 1),
        ("Need a leaf cleanup ASAP please help.", 1),
        ("How do I find a contractor for a bathroom remodel?", 1),
        ("ISO a general contractor for an addition to my home.", 1),
        ("Who can I hire for odd jobs around the house?", 1),
        ("Need a handyman available weekends for small projects.", 1),


        # =========================================================
        # SELLERS — Label: 0  (Advertising / promoting services)
        # =========================================================

        # --- Landscaping ---
        ("We provide professional landscaping services at the best rates.", 0),
        ("Affordable lawn care packages starting at $40.", 0),
        ("Local business offering tree removal and pruning.", 0),
        ("Spring cleanup specials available now, call for a free estimate.", 0),
        ("We offer weekly and biweekly lawn maintenance programs.", 0),
        ("Licensed landscaper serving the area for over 10 years.", 0),
        ("Get your yard looking great — we handle mowing, edging, and more.", 0),
        ("Now booking spring landscaping clients, limited slots available!", 0),
        ("We do full landscape design and installation.", 0),
        ("Leaf removal and fall cleanup specials starting this week.", 0),
        ("Residential and commercial lawn care, fully insured.", 0),
        ("Call us for sod installation, grading, and drainage solutions.", 0),
        ("Mulching and bed maintenance packages available now.", 0),
        ("We are expanding our lawn care routes, taking new clients.", 0),
        ("Free estimates on all landscaping work, message us today.", 0),

        # --- Painting ---
        ("Licensed and insured painter available for interior and exterior.", 0),
        ("I do painting and drywall at a low cost.", 0),
        ("Professional painters serving this area, message for a quote.", 0),
        ("Interior and exterior painting, competitive pricing.", 0),
        ("We use premium paints and guarantee our work.", 0),
        ("Fully insured painting company, residential and commercial.", 0),
        ("Cabinet refinishing and full home painting available.", 0),
        ("Book your spring exterior paint job now while slots last.", 0),
        ("15 years of painting experience, no job too small.", 0),
        ("We specialize in color consultation and premium finishes.", 0),
        ("Deck staining and fence painting at affordable rates.", 0),
        ("Family-owned painting business serving this community since 2005.", 0),
        ("Free color samples provided with every estimate.", 0),
        ("Rental property painting specialists, fast turnaround.", 0),
        ("Follow our page for before and after painting transformations!", 0),

        # --- Asphalt Paving ---
        ("Message me for a quote on your new driveway.", 0),
        ("Professional asphalt paving and sealcoating services.", 0),
        ("We specialize in residential and commercial paving projects.", 0),
        ("Driveway sealcoating starting at $99, book now!", 0),
        ("Licensed paving contractor with 20 years of experience.", 0),
        ("Crack filling and asphalt repair at competitive rates.", 0),
        ("Now booking spring paving season, call for a free estimate.", 0),
        ("We handle parking lot striping and ADA compliance work.", 0),
        ("Our paving crews are fully insured and bonded.", 0),
        ("Check out our recent driveway paving projects on our page.", 0),

        # --- Carpentry ---
        ("Years of experience in carpentry and custom woodwork.", 0),
        ("Expert mason available for stone walls and patios.", 0),
        ("Check out our portfolio of custom decks and patios.", 0),
        ("Custom cabinet and built-in specialist, message for details.", 0),
        ("We build custom pergolas, decks, and outdoor structures.", 0),
        ("Trim carpentry and finish work at fair prices.", 0),
        ("Licensed carpenter available for residential projects.", 0),
        ("We offer free design consultations for custom woodwork.", 0),
        ("Hardwood stairs and railings are our specialty.", 0),
        ("Small carpentry repairs to full renovations, we do it all.", 0),

        # --- Kitchen & Bath ---
        ("We specialize in custom kitchen and bath renovations.", 0),
        ("Professional kitchen remodeling services at great rates.", 0),
        ("Bathroom renovation experts. Licensed and insured.", 0),
        ("Full kitchen and bath design/build company.", 0),
        ("Free design consultations for your next kitchen update.", 0),
        ("Quality bathroom remodeling — see our latest projects!", 0),
        ("Expert cabinet installation and countertop services.", 0),
        ("Transform your kitchen with our renovation packages.", 0),
        ("Licensed contractor for all your kitchen and bath needs.", 0),
        ("Follow us for kitchen and bath renovation inspiration.", 0),

        # --- Plumbing ---
        ("Licensed and insured plumber available 24/7.", 0),
        ("Expert plumbing repairs, leaks, and drain cleaning.", 0),
        ("We install water heaters, sump pumps, and more.", 0),
        ("Emergency plumbing services — call now for help.", 0),
        ("Professional plumbing at affordable prices.", 0),
        ("Your local neighborhood plumber with 20 years experience.", 0),
        ("We handle all residential and commercial plumbing.", 0),
        ("Sewer line repair and replacement specialists.", 0),
        ("Contact us for all your plumbing and heating needs.", 0),
        ("Free estimates on any plumbing project, big or small.", 0),

        # --- Electrical ---
        ("Licensed master electrician for all your home wiring.", 0),
        ("We do panel upgrades, EV chargers, and lighting.", 0),
        ("Safe and reliable electrical services, fully insured.", 0),
        ("Expert electrical troubleshooting and repairs.", 0),
        ("Upgrade your home's electrical system with our team.", 0),
        ("Licensed electrical contractor available for new installs.", 0),
        ("Generator installations and emergency electrical work.", 0),
        ("Professional electricians serving the local community.", 0),
        ("Free quotes on lighting and outlet installations.", 0),
        ("Energy-efficient electrical solutions for your home.", 0),

        # --- Fence Installation & Repair ---
        ("We install wood, vinyl, chain link, and aluminum fences.", 0),
        ("Free fence estimates, fully licensed and insured.", 0),
        ("Fence repair and replacement at affordable prices.", 0),
        ("We are a local fencing company with hundreds of installs.", 0),
        ("Spring fencing special — book now and save 10%.", 0),
        ("Licensed fence contractor serving residential and commercial.", 0),
        ("We handle all permits for fence installations.", 0),
        ("Message us for a free fencing consultation.", 0),
        ("Check out our recent fence projects on our Facebook page.", 0),
        ("Quality fencing guaranteed, follow us to see our work.", 0),

        # --- Flooring ---
        ("Follow our page to see our latest flooring projects.", 0),
        ("We install hardwood, LVP, tile, and carpet.", 0),
        ("Free flooring estimates, call or text anytime.", 0),
        ("Flooring installation and refinishing at competitive rates.", 0),
        ("Licensed flooring contractor with 15 years of experience.", 0),
        ("We carry a wide selection of flooring materials in stock.", 0),
        ("Tile and hardwood installation, fully insured crew.", 0),
        ("Check our Instagram for before and after flooring transformations.", 0),
        ("Whole-home flooring packages available at discounted rates.", 0),
        ("Move-in ready flooring services, fast turnaround guaranteed.", 0),

        # --- Cleaning ---
        ("Best cleaning service in town, book now and save 20%.", 0),
        ("Professional house cleaning, we bring our own equipment.", 0),
        ("We are hiring new team members for our cleaning crew.", 0),
        ("Residential and commercial cleaning, fully bonded and insured.", 0),
        ("Book a deep clean today and get your second visit 50% off.", 0),
        ("We offer move-in, move-out, and recurring cleaning services.", 0),
        ("Eco-friendly cleaning products used on every job.", 0),
        ("Our cleaning team is background-checked and verified.", 0),
        ("Post-construction and renovation cleaning is our specialty.", 0),
        ("We serve Airbnb hosts with same-day turnover cleaning.", 0),
        ("Join our mailing list for updates on our services.", 0),
        ("Quality service guaranteed, licensed and bonded company.", 0),
        ("Serving the entire city for all your maintenance needs.", 0),

        # --- Snow Removal ---
        ("We specialize in snow removal for residential and commercial.", 0),
        ("Seasonal snow contracts now available, limited spots!", 0),
        ("We offer per-push and seasonal snow removal pricing.", 0),
        ("Our plowing crew is on call 24/7 during storm events.", 0),
        ("Sign up for our snow removal list before the season starts.", 0),

        # --- General ---
        ("Call us today for a free estimate on your roofing project.", 0),
        ("I am an experienced handyman serving the community.", 0),
        ("Contact me for all your plumbing needs, 24/7 service.", 0),
        ("We are hiring new technicians to join our growing team.", 0),


        # =========================================================
        # NOISE — Label: 0  (Irrelevant / not contractor-related)
        # =========================================================
        ("Obituary: Rest in peace John Smith.", 0),
        ("Join our group for community discussions.", 0),
        ("Lost dog found in the neighborhood.", 0),
        ("Garage sale this Saturday at 10 AM.", 0),
        ("Looking for my lost keys near Central Park.", 0),
        ("Don't forget the town hall meeting tomorrow.", 0),
        ("Happy birthday to my lovely wife!", 0),
        ("Selling my old tools and equipment, DM me.", 0),
        ("Who wants to go to the concert tonight?", 0),
        ("New restaurant opening on Main St.", 0),
        ("Has anyone tried the new Thai place on Elm Street?", 0),
        ("Free kittens to a good home!", 0),
        ("Can anyone recommend a good babysitter?", 0),
        ("Does anyone know the wifi password for the community center?", 0),
        ("Selling a used couch, great condition, $150.", 0),
        ("Anyone interested in joining a neighborhood book club?", 0),
        ("Community park cleanup event this Sunday!", 0),
        ("Police activity reported on Oak Street, avoid the area.", 0),
        ("Looking for recommendations for a good dentist.", 0),
        ("Happy New Year to all my neighbors!", 0),
        ("My car was broken into last night, stay alert.", 0),
        ("Fundraiser for the local school this Friday night.", 0),
        ("Anyone know a good vet in the area?", 0),
        ("Selling tickets to the upcoming charity dinner.", 0),
        ("Local election results are in!", 0),
        ("Has anyone seen a stray cat around Pine Ave?", 0),
        ("Does anyone want fresh vegetables from my garden?", 0),
        ("Reminder: street sweeping tomorrow, move your cars.", 0),
        ("ISO a good mechanic for my car, not home repairs.", 0),
        ("Can someone recommend a good hair salon?", 0),
        ("Does anyone know a reliable dog walker?", 0),
        ("Power outage reported on the east side of town.", 0),
        ("Selling a barely used treadmill, asking $200.", 0),
        ("Anyone want free moving boxes?", 0),
        ("Lost and found: Gold bracelet near the park.", 0),
        ("My neighbor's fireworks are too loud!", 0),
        ("Vote for Smith in the upcoming school board election.", 0),
        ("Anyone else notice the potholes on Main Street?", 0),  # complaint, not a hire request
        ("The new coffee shop downtown is amazing!", 0),
        ("Reminder about the condo association meeting Thursday.", 0),
    ]




    def __init__(self):
        self._pipeline = None
        self._load_or_train()

    def _clean_text(self, text: str) -> str:
        """Standard preprocessing for intent detection."""
        if not text: return ""
        text = text.lower()
        # Remove URLs and Phone numbers as they are often associated with spam/sellers
        text = re.sub(r'http\S+|www\.\S+|\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b', '', text)
        return text.strip()

    def _load_or_train(self):
        """Train the model if the joblib file doesn't exist."""
        if os.path.exists(self.MODEL_PATH):
            try:
                self._pipeline = joblib.load(self.MODEL_PATH)
                return
            except Exception:
                pass

        # Training
        print("Training Buyer Intent ML Model...")
        texts, labels = zip(*self.TRAINING_DATA)
        cleaned_texts = [self._clean_text(t) for t in texts]

        # Pipeline: TF-IDF + Logistic Regression (Very efficient on CPU)
        self._pipeline = Pipeline([
            ('tfidf', TfidfVectorizer(ngram_range=(1, 2), max_features=1000)),
            ('clf', LogisticRegression(random_state=42, C=10.0))
        ])

        self._pipeline.fit(cleaned_texts, labels)
        
        # Save for persistence
        try:
            joblib.dump(self._pipeline, self.MODEL_PATH)
        except Exception:
            pass

    def predict_intent(self, text: str, threshold: float = 0.40) -> Dict[str, Any]:
        """Classify post intent with adjustable threshold."""
        if not self._pipeline:
            return {"is_buyer": False, "score": 0.0, "reason": "Model unavailable"}

        cleaned = self._clean_text(text)
        if not cleaned or len(cleaned) < 5:
            return {"is_buyer": False, "score": 0.0, "reason": "Text too short"}

        # Get probability
        prob = self._pipeline.predict_proba([cleaned])[0]
        buyer_score = float(prob[1])
        
        # We use a custom threshold since we want to be sensitive to buyers
        is_buyer = buyer_score >= threshold

        return {
            "is_buyer": is_buyer,
            "score": round(buyer_score, 3),
            "reason": "ML Above Threshold" if is_buyer else "ML Below Threshold"
        }

    def is_buyer_request(self, text: str, **kwargs) -> bool:
        """Integration method."""
        return self.predict_intent(text)["is_buyer"]

if __name__ == "__main__":
    detector = BuyerMLDetector()
    test_cases = [
        "Need help with leaf removal this weekend in Chelsea",
        "I offer the best landscaping services in Brooklyn, licensed and insured!",
        "Can anyone recommend a good painter? I have 3 rooms to do.",
        "ISO someone to fix a broken fence post ASAP.",
        "Contact us for a free estimate on your roofing project. We do all types of roofs.",
        "Obituary: John Doe passed away peacefully...",
        "Looking for a reliable person to mow my yard weekly.",
        "Plumbing service 24/7, licensed and bonded plumbers. 123-456-7890",
        "ISO referral for a good mason to build a retaining wall.",
        "Looking to hire someone for painting work."
    ]

    print(f"\n{'Prediction':<12} | {'Score':<6} | {'Text'}")
    print("-" * 100)
    for t in test_cases:
        r = detector.predict_intent(t)
        p = "BUYER" if r['is_buyer'] else "SELLER/NOISE"
        print(f"{p:<12} | {r['score']:<6.3f} | {t[:70]}...")
