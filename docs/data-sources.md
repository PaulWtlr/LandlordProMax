# Data Sources

## Sources prioritaires

- HM Land Registry Price Paid Data: prix realises, source officielle.
- EPC Register: efficacite energetique et surface quand disponible.
- ONS / Open Geography Portal: geographies, LSOA, boroughs.
- TfL: accessibilite transport.

## Listings live

Rightmove et Zoopla ne doivent pas etre scrappes automatiquement sans autorisation contractuelle ou API/licence explicite.

L'outil accepte donc des listings via:

- API autorisee;
- export CSV/JSON;
- HTML fourni par l'utilisateur si son usage est autorise;
- connecteur custom pour une source qui autorise explicitement la collecte.

## Zone cible

La premiere version est volontairement limitee a:

- Chelsea;
- South Kensington.

Cette contrainte reduit le bruit et permet de calibrer les signaux micro-locaux avant d'etendre a d'autres quartiers prime London.

