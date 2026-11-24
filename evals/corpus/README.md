# Evaluation corpus

The files in `pages/` are text extracted from public web pages, saved so that every evaluation
result can be reproduced from this repository. They are not covered by the repository's own
licence. Each file records its `url`, the date it was fetched, a hash of the text, and its licence:

| Source | Licence |
|---|---|
| Wikipedia (`en.wikipedia.org`) | Creative Commons Attribution-ShareAlike 4.0. Text by Wikipedia contributors; the `url` field links to each article and its history. |
| Our World in Data (`ourworldindata.org`) | Creative Commons Attribution 4.0. |
| United States government sites (`.gov`) | Public domain as works of the US government. |

The text is unedited apart from extraction: page chrome is removed, whitespace is collapsed, and
articles longer than 60,000 characters are cut at a paragraph break.

Pages were fetched with the project's own fetcher, which obeys `robots.txt`, waits two seconds
between requests to a site, and identifies itself with the repository's address.
