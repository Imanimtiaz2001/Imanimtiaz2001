"""Small, reviewed starter catalogue. Costs are planning estimates, not ticket quotes."""

from urllib.parse import quote

from app.models import Activity, Evidence

# IATA codes are used only for optional provider lookups. Everything else works without them.
# tuple: name, interest tags, hours, entry estimate per person, indoor, short description
DESTINATIONS = {
    "istanbul": ("Istanbul, Türkiye", "IST", 65, [
        ("Hagia Sophia", "history architecture", 1.5, 0, True, "Explore the historic landmark; check current visitor access and ticket rules."),
        ("Grand Bazaar", "shopping culture food", 2, 0, True, "Browse the covered market and its surrounding lanes."),
        ("Topkapı Palace", "history art architecture", 3, 45, True, "Explore palace courtyards and museum collections."),
        ("Bosphorus waterfront", "nature photography culture", 2, 0, False, "Walk the waterfront and watch the ferries."),
        ("Istanbul Archaeological Museums", "history museums art", 2, 22, True, "Visit the archaeology collections."),
        ("Galata Tower district", "photography architecture food", 2, 30, False, "Walk the neighborhood; tower admission is optional."),
        ("Süleymaniye Mosque", "architecture history", 1.5, 0, True, "Visit respectfully outside prayer times."),
    ]),
    "tokyo": ("Tokyo, Japan", "TYO", 125, [
        ("Sensō-ji Temple", "history culture architecture", 2, 0, False, "Explore Asakusa and the temple approach."),
        ("Shibuya Crossing", "photography culture shopping", 1.5, 0, False, "Walk Shibuya and its surrounding streets."),
        ("Meiji Jingū", "nature history culture", 2, 0, False, "Walk the forested shrine paths."),
        ("Tokyo National Museum", "museums art history", 3, 15, True, "Explore Japanese art and archaeology."),
        ("Tsukiji Outer Market", "food shopping culture", 2, 0, False, "Browse food stalls; meals are budgeted separately."),
        ("Shinjuku Gyoen", "nature photography", 2, 5, False, "Relax in the gardens; check seasonal hours."),
        ("Akihabara", "shopping technology culture", 2, 0, True, "Explore electronics and pop culture shops."),
    ]),
    "paris": ("Paris, France", "PAR", 150, [
        ("Eiffel Tower gardens", "architecture photography nature", 2, 0, False, "Enjoy the public gardens; tower access costs extra."),
        ("Louvre Museum", "art museums history", 3, 35, True, "Visit selected galleries; reserve entry ahead."),
        ("Montmartre", "art culture photography", 2, 0, False, "Explore hillside streets and viewpoints."),
        ("Musée d'Orsay", "art museums", 2.5, 20, True, "See the nineteenth-century art collections."),
        ("Jardin du Luxembourg", "nature relaxation", 2, 0, False, "Take a relaxed garden walk."),
        ("Le Marais", "food shopping culture", 2, 0, False, "Explore historic streets and independent shops."),
        ("Notre-Dame de Paris", "history architecture", 1.5, 0, True, "Visit the cathedral area; check access in advance."),
    ]),
    "rome": ("Rome, Italy", "ROM", 110, [
        ("Colosseum", "history architecture", 2.5, 25, False, "See the amphitheater; reserve official entry."),
        ("Roman Forum", "history architecture", 2, 18, False, "Walk the archaeological area."),
        ("Vatican Museums", "art museums history", 3, 30, True, "Explore the collections with a timed ticket."),
        ("Trevi Fountain", "photography architecture", 1, 0, False, "Take a short walk around the fountain area."),
        ("Trastevere", "food culture", 2, 0, False, "Explore neighborhood streets and cafés."),
        ("Pantheon", "history architecture", 1.5, 7, True, "Visit the ancient landmark; verify admission."),
        ("Villa Borghese gardens", "nature relaxation", 2, 0, False, "Take a park walk."),
    ]),
    "london": ("London, United Kingdom", "LON", 170, [
        ("British Museum", "museums history art", 3, 0, True, "Explore the permanent collection; special exhibitions vary."),
        ("South Bank", "photography food culture", 2, 0, False, "Walk the Thames riverside."),
        ("Tower of London", "history architecture", 3, 45, True, "Explore the fortress and exhibitions."),
        ("National Gallery", "art museums", 2, 0, True, "Visit the permanent art collection."),
        ("Hyde Park", "nature relaxation", 2, 0, False, "Enjoy a walk through the park."),
        ("Borough Market", "food shopping", 1.5, 0, True, "Browse food stalls; meals are budgeted separately."),
        ("Covent Garden", "shopping culture", 2, 0, False, "Explore shops and nearby streets."),
    ]),
    "dubai": ("Dubai, UAE", "DXB", 150, [
        ("Al Fahidi Historical Neighbourhood", "history culture architecture", 2, 0, False, "Walk restored lanes and courtyards."),
        ("Dubai Creek abra crossing", "culture photography", 1.5, 3, False, "Cross the creek; fare is an estimate."),
        ("Dubai Mall", "shopping food", 2, 0, True, "Explore the indoor shopping district."),
        ("Museum of the Future", "technology museums", 2, 45, True, "Visit exhibits with advance tickets."),
        ("Jumeirah Beach", "beach nature relaxation", 2, 0, False, "Relax at the public beach."),
        ("Dubai Frame", "architecture photography", 1.5, 15, True, "See panoramic city views."),
        ("Gold and Spice Souks", "shopping culture", 2, 0, False, "Walk the traditional market streets."),
    ]),
    "bangkok": ("Bangkok, Thailand", "BKK", 65, [
        ("Grand Palace", "history architecture culture", 3, 20, False, "Explore the complex; follow the dress code."),
        ("Wat Pho", "history architecture", 2, 10, True, "Visit the temple complex."),
        ("Chatuchak Market", "shopping food culture", 2.5, 0, False, "Browse stalls; check opening days."),
        ("Lumphini Park", "nature relaxation", 2, 0, False, "Enjoy a park walk."),
        ("Bangkok Art and Culture Centre", "art museums", 2, 0, True, "Explore contemporary exhibitions."),
        ("Chao Phraya riverside", "photography culture", 2, 5, False, "Walk the riverfront; boat fare is estimated."),
        ("Jim Thompson House", "history art", 2, 8, True, "Visit the heritage house museum."),
    ]),
    "barcelona": ("Barcelona, Spain", "BCN", 120, [
        ("Sagrada Família", "architecture history art", 2, 35, True, "Visit with a timed ticket."),
        ("Park Güell", "art architecture nature", 2.5, 18, False, "Walk the gardens and monumental area."),
        ("Gothic Quarter", "history photography culture", 2, 0, False, "Explore historic streets."),
        ("Picasso Museum", "art museums", 2, 15, True, "Explore the permanent collection."),
        ("Barceloneta Beach", "beach relaxation", 2, 0, False, "Relax on the waterfront."),
        ("La Boqueria", "food shopping", 1.5, 0, True, "Browse market stalls; meals are separate."),
        ("Montjuïc gardens", "nature photography", 2, 0, False, "Walk the hillside gardens."),
    ]),
    "singapore": ("Singapore", "SIN", 160, [
        ("Gardens by the Bay outdoor gardens", "nature photography", 2, 0, False, "Explore free outdoor areas; conservatories cost extra."),
        ("National Gallery Singapore", "art museums", 2.5, 25, True, "Explore Southeast Asian art."),
        ("Chinatown", "food culture shopping", 2, 0, False, "Walk heritage streets and markets."),
        ("Singapore Botanic Gardens", "nature relaxation", 2, 0, False, "Visit the public gardens."),
        ("ArtScience Museum", "art technology museums", 2, 25, True, "Visit current exhibitions; prices vary."),
        ("Marina Bay waterfront", "photography architecture", 2, 0, False, "Enjoy a waterfront walk."),
        ("Little India", "food culture", 2, 0, False, "Explore shops and colorful streets."),
    ]),
    "lisbon": ("Lisbon, Portugal", "LIS", 100, [
        ("Belém Tower", "history architecture", 1.5, 15, False, "Visit the riverfront monument; access may change."),
        ("Alfama", "culture photography", 2, 0, False, "Walk the hillside lanes."),
        ("Jerónimos Monastery", "history architecture", 2, 20, True, "Visit the cloisters with a ticket."),
        ("Calouste Gulbenkian Museum", "art museums", 2, 15, True, "Explore art collections."),
        ("Time Out Market", "food shopping", 1.5, 0, True, "Browse food stalls; meals are separate."),
        ("Miradouro da Senhora do Monte", "photography nature", 1.5, 0, False, "Enjoy a city viewpoint."),
        ("Parque Eduardo VII", "nature relaxation", 2, 0, False, "Take a city park walk."),
    ]),
}


def get_destination(name: str):
    normalized = " ".join(name.casefold().strip().split())
    aliases = {"istanbul, turkey": "istanbul", "london, uk": "london",
               "dubai, united arab emirates": "dubai"}
    if normalized in aliases:
        return DESTINATIONS[aliases[normalized]]
    for key, data in DESTINATIONS.items():
        if normalized in (key, data[0].casefold()):
            return data
    return None


def activities_for(name: str) -> list[Activity]:
    data = get_destination(name)
    if data is None:
        return []
    label, _, _, records = data
    return [
        Activity(
            name=title, category=tags, duration_hours=hours,
            estimated_cost_usd=cost, indoor=indoor, description=description,
            map_url=f"https://www.google.com/maps/search/?api=1&query={quote(title + ', ' + label)}",
            evidence=Evidence(source="Wayfinder reviewed place catalogue", kind="catalogue",
                              note="Place exists; hours, tickets and access must be checked."),
        )
        for title, tags, hours, cost, indoor, description in records
    ]
