"""Runs before any AI model sees a customer's text: does it say that a person was hurt?

A claim that involves an injury is for a claims handler from the start. Its text is not sent to the models:
what a customer writes about someone's health is the most sensitive information a claim can hold.

This is a word list in English and Dutch, not understanding. It catches the usual wording, not every phrasing,
misspelling or other language. The chat model is still told to hand over when someone was injured, as a second
layer for what the list misses.
"""
import re

# Why a model call was skipped. Shown to the claims handler in the rule results.
NOT_FOR_AI = "No AI assessment: someone may have been hurt, so a claims handler handles this claim"

_THING = r"(?:battery|engine|phone|mobile|alternator|starter)"          # things nobody sits in
_DING = r"(?:accu|batterij|telefoon)"
_WENT = r"(?:['’]s| is| was| went| has gone| has| had| just| suddenly)?"
# Wording that says nobody was hurt, or uses a harm word for something else. Taken out before the check.
_NO_HARM = [
    r"(?:no ?one|no-one|nobody|none of (?:us|them)|neither of (?:us|them))(?:['’]s)?(?: else)?"
    r"(?: (?:in|from|inside) (?:the |my |our |either |both |any )?(?:other )?(?:cars?|vehicles?|van))?"
    r"\s+(?:was|were|got|is|has been|had been)?\s*(?:hurt|injured|harmed|wounded)",
    r"no (?:one |body )?(?:got |was )?(?:hurt|injured)",
    r"no injur(?:y|ies)", r"without (?:any )?injur(?:y|ies)",
    r"(?:was|were|is|are|am)(?: not|n't|n’t) (?:hurt|injured|harmed)", r"not (?:hurt|injured|harmed)",
    r"did(?: not|n't|n’t|nt) (?:get )?(?:hurt|injured)",
    r"uninjured", r"unhurt", r"unharmed",
    r"no (?:ambulance|doctor|hospital|paramedics?) (?:was |were )?(?:needed|required|necessary|called|involved)",
    r"no need for (?:an? |the )?(?:ambulance|doctor|hospital|paramedics?)",
    rf"dead[- ](?:battery|end|stop|cent(?:re|er)|slow|straight|ahead|fox|deer|badger|bird|cat|dog|animal|rabbit|tree|branch|car|{_THING})",
    r"stop(?:ped|s)? dead",
    r"(?:parked|parking|car ?park|garage)(?: of| at| by| outside| near| in front of| next to| behind| opposite)* (?:the |my |a |our )?"
    r"(?:[\w.'’-]+ ){0,3}?(?:hospital|doctor(?:['’]s)?(?: surgery| office| practice)?)",
    r"(?:geparkeerd|parkeer\w*)(?: stond| staan)? (?:voor|bij|naast|achter|tegenover|van) (?:het |de |een |mijn )?"
    r"(?:[\w.'’-]+ ){0,2}?(?:ziekenhuis|huisarts(?:enpost|enpraktijk)?|dokter)",
    r"(?:let|letting|make way for|made way for|gave way to|give way to|pulled over for|moved over for) an? ambulance"
    r"(?: pass| through| by| past)?",
    r"(?:car|van|vehicle|engine|battery) (?:is|was) (?:now |completely |totally |stone )dead",
    r"(?:accu|batterij|motor) (?:is|was) (?:nu |helemaal )(?:dood|leeg)",
    r"(?:at|on|in) the back (?:is|was|got|are|were) broken",
    rf"{_THING}{_WENT} (?:dead|died)",
    # "my car died", but not "the driver of the car died"
    rf"(?<!of )(?<!in )(?<!from )(?:my|the|our|his|her) car{_WENT} (?:dead|died)",
    r"killed (?:the|my|his|her) (?:(?:front|rear|back|left|right) )?(?:engine|battery|tyre|tire|car|suspension|clutch|"
    r"gearbox|motor|alloy|wheel|rim)(?! ?(?:driver|passenger|occupant|owner))",
    r"(?:scared|frightened|worried|bored|sick) (?:me |us |him |her )?(?:half )?to death",
    r"hurts? (?:my|the|our) (?:wallet|pocket|bank balance|pride|no[- ]claims\w*)",
    r"bloody (?:thing|car|idiot|hell|door|van|driver|fool|nightmare|stupid|useless|annoying|typical|well|lorry|truck|"
    r"bike|taxi|bus|pothole|kerb|bollard|post|gate|wall|machine|app|form|awful|ridiculous)",
    r"wound (?:(?:the|my|his|her) windows? )?(?:down|up)",
    r"(?:is|was|been|what|such) a (?:real |total |massive |bit of a )?headache",
    r"arts (?:building|centre|center|faculty|school|college|council|theatre)|(?:martial|fine|performing|liberal) arts",
    r"hospital (?:car ?park|parking(?: lot| garage)?|garage)", r"(?:car ?park|parking(?: lot| garage)?) (?:of|at|near|by) (?:the |a )?hospital",
    r"(?-i:Hospital (?:Road|Rd|Street|Lane|Avenue|Ave))",
    r"niemand\s+(?:is |was |raakte |werd )?(?:er )?(?:gelukkig )?(?:gewond|verwond)(?: geraakt)?",
    r"niemand (?:heeft|had|liep) (?:lichamelijk |persoonlijk )?letsel(?: opgelopen)?",
    r"geen (?:gewonden|(?:lichamelijk |persoonlijk )?letsel(?:schade)?|verwondingen)", r"niet (?:gewond|verwond)", r"ongedeerd",
    r"zonder (?:letsel|verwondingen|gewonden)",
    r"geen (?:ambulance|dokter|arts|ziekenhuis) nodig", r"hoefden? geen (?:ambulance|dokter|arts)",
    rf"{_DING}(?: is| was| ging)? (?:dood|leeg)",
    r"(?:ik ben|ben ik|ik werd|wij zijn|we zijn) (?:het )?slachtoffer (?:geworden )?van (?:een |de )?"
    r"(?:doorrijder|vandalisme|diefstal|inbraak|oplichting|fraude|parkeerschade)",
    r"ziekenhuis ?(?:parkeer\w*|garage)", r"parkeer\w* (?:van|bij|naast) (?:het |een )?ziekenhuis",
]
# "I was not hurt but my wife was", "niemand gewond behalve de fietser": the denial is followed by an exception,
# so it is not taken out and the harm word in it counts.
_EXCEPTION_RE = re.compile(
    r"[^.!?;]{0,30}?(?:\bbut\b[^.!?;]{1,40}?\b(?:was|were|is|are|did|has|have)\s*(?:[.!?;,]|$)"
    r"|\bmaar\b[^.!?;]{1,40}?\bwel\s*(?:[.!?;,]|$)"
    r"|\b(?:except|apart from|other than|besides|behalve)\b)", re.IGNORECASE)

_BODY = (r"(?:arms?|legs?|ribs?|nose|wrists?|ankles?|neck|back|collar ?bone|hips?|jaw|fingers?|hands?|foot|feet|bones?|"
         r"skull|shoulders?|knees?|elbows?|toes?|thumbs?|pelvis|spine)")
# "broken back window", "broken hand brake", "arm rest": the car, not a person
_NOT_CAR = (r"(?! ?(?:rest|window|windscreen|screen|lights?|lamp|bumper|door|seat|axle|wheel|tyre|tire|brake|panel|end|box|"
            r"bar|wiper|mirror|glass|passenger|quarter|arch|wing|corner|side|of the (?:car|van))s?\b)")
_ADJ = r"(?:left |right |lower |upper |both |two |three |\d+ )?"
_LICHAAM = r"(?:arm|been|rib|ribben|neus|pols|enkel|nek|rug|sleutelbeen|heup|kaak|vinger|hand|voet|bot|schedel|schouder|knie)"
_PERSON = r"(?:pedestrian|cyclist|child|kid|person|man|woman|boy|girl|baby)"
_ROAD_USER = r"(?:pedestrian|cyclist|motorcyclist|biker|rider|jogger|child|kid|boy|girl|baby|toddler)"
_PERSOON = r"(?:voetganger|fietser|fietsster|kind|persoon|man|vrouw|jongen|meisje|baby)"
_HARM = [
    # English
    r"injur(?:y|ies|ed|ing)", r"hurt(?:s|ing|ed)?", r"wound(?:s|ed)?", r"bleed(?:s|ing)?", r"bled", r"blood(?:y|ied)?",
    r"hosp(?:ital|tial|itle)?(?:s|ised|ized|isation|ization)?", r"ambul[ae]nce\w*", r"(?:para)?medics?", r"wh?ip ?lash",
    r"concussion", r"unconscious",
    r"fractur(?:e|es|ed)", r"stitches", r"bruis(?:e|es|ed|ing)", r"sprain(?:ed)?", r"dislocated",
    r"casualt(?:y|ies)", r"fatal(?:ity|ities|ly)?", r"died", r"dead", r"death", r"killed", r"passed away",
    r"emergency room", r"a&e", r"(?:to|in|at) (?:the )?(?-i:ER|ICU)", r"intensive care", r"first aid", r"do[ck]t[eo]rs?",
    r"medical (?:help|attention|treatment|care)", r"painkillers?", r"physio\w*", r"x-?rays?", r"crutches",
    r"in (?:a lot of |so much |severe |great |some |terrible |real |constant )?pain",
    r"pain in (?:my|his|her|their|our|both) (?:neck|back|chest|head|shoulders?|knees?|legs?|arms?|ribs?|hips?|wrists?|ankles?|side|stomach)",
    r"(?:neck|back|chest|head|shoulder|knee|leg|arm) ?(?:pain|ache)", r"headaches?", r"nose ?bleeds?",
    r"sore (?:neck|back|chest|head|shoulders?|knees?|legs?|arms?|ribs?|wrists?|ankles?)",
    rf"brok(?:e|en) (?:his |her |my |their |our |the |a |an )?{_ADJ}{_BODY}{_NOT_CAR}",
    rf"(?<!wiper )(?<!control )(?<!mirror )(?<!suspension ){_BODY} (?:is|was|got|are|were) broken",
    rf"(?:burn(?:ed|t)|cut|twisted|strained|banged|bumped) (?:my|his|her|their|our) (?:{_BODY}|head|face|chest|forehead|eyes?|lip|chin|cheek){_NOT_CAR}",
    rf"hit (?:a|an|the|some) {_PERSON}(?!['’]s)", rf"ran over (?:a|an|the|my|his|her|some) {_PERSON}",
    r"hit (?:someone|somebody) (?:crossing|walking|on (?:a|the|his|her) (?:bike|bicycle|scooter|crossing))",
    rf"{_ROAD_USER} (?:was|got|has been|had been) (?:hit|struck|knocked (?:down|over)|run over)",
    r"(?:ran|run|knocked) (?:him|her|them|someone|somebody) (?:over|down)",
    # Dutch
    r"(?:zwaar|licht)?gewon[dt](?:e|en)?", r"verwond(?:e|en|ing|ingen)?", r"\w*letsel\w*",
    r"bloed(?:en|end|ende|de|t|ing|ingen|neus)?", r"(?:hoofd|snij|schaaf|vlees)?wond(?:en|je|jes)?",
    r"ziekenhui[sz](?:en|opname|bezoek)?", r"zkh", r"ziekenwagen",
    r"hersenschudding", r"bewusteloos", r"buiten bewustzijn", r"buiten westen", r"kneuzing(?:en)?", r"gekneusde?",
    r"hechtingen", r"gehecht(?! aan)", r"(?:in|het) gips", r"geblesseerde?", r"blessures?",
    r"overleden", r"gestorven", r"omgekomen", r"om het leven gekomen", r"dood", r"doden", r"dodelijke?",
    r"slachtoffers?",
    r"spoedeisende hulp", r"seh", r"eerste hulp", r"ehbo", r"arts(?:en)?", r"huisarts(?:en|enpost)?", r"fysio\w*",
    r"pijnstillers?",
    r"(?:nek|rug|hoofd|borst|schouder|knie) ?pijn", r"(?:nek|rug|hoofd|schouder|knie|pijn)klachten",
    r"pijn (?:aan|in)", r"veel pijn", r"pijn gedaan", r"zeer gedaan",
    r"(?:doet|deed|doen|deden) (?:nog (?:steeds )?|erg |heel |veel |zo )?(?:pijn|zeer)",
    r"(?:heb|heeft|hebben|had|hadden) (?:nog (?:steeds )?|erg |erge |veel |hevige |wat |nu )?pijn",
    r"last van (?:mijn|m'n|mn|me|zijn|z'n|haar|de|het) (?:nek|rug|hoofd|schouder|knie|pols|been|arm|heup)",
    r"bezeerd", rf"gebroken {_LICHAAM}", rf"{_LICHAAM} (?:is |was )?gebroken",
    rf"brak (?:zijn|z'n|haar|mijn|m'n|mn|de|het|een) {_LICHAAM}",
    rf"{_PERSOON} (?:is |was |werd )?(?:aangereden|geschept|omvergereden)", rf"(?:aangereden|geschept) {_PERSOON}",
]
_NO_HARM_RE = re.compile("|".join(rf"\b(?:{p})\b" for p in _NO_HARM), re.IGNORECASE)
_HARM_RE = re.compile("|".join(rf"(?<![\w&])(?:{p})(?![\w&])" for p in _HARM), re.IGNORECASE)


# In an address these are buildings and street names ("Maasstad Ziekenhuis", "Doctor Molewaterplein"), not injuries
_PLACE_NAMES = re.compile(r"\b(?:hospital|ziekenhuis|doctor|dokter|dr|huisarts\w*|arts)\b\.?", re.IGNORECASE)


def place_text(place):
    """A "where did it happen" answer with building and street names taken out, ready for mentions_injury."""
    return _PLACE_NAMES.sub(" ", str(place or ""))


def mentions_injury(text):
    """The words in `text` that say a person was hurt, or None."""
    text = str(text or "")
    cleaned = _NO_HARM_RE.sub(lambda m: m.group(0) if _EXCEPTION_RE.match(text, m.end()) else " ", text)
    match = _HARM_RE.search(cleaned)
    return match.group(0).lower() if match else None
