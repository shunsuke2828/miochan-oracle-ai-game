# Miochan production acceptance load test

The k6 scenario uses the public API Gateway URL and creates non-public,
non-ranking participants. Each VU creates one participant, submits a survey,
plays one 60-second rescue game, and then sustains state polling until the end
of the acceptance window.

Session identifiers are printed with the `__MIO_SESSION__` marker. Cleanup is
additionally guarded by the exact nickname prefix and never deletes seed rows.

For the retained-data acceptance run, do not execute `cleanup_mio_loadtest.py`.
The generated participants use `public_consent=false` and
`ranking_consent=false`, so retained test rows are excluded from the public map
and rescue ranking.

The production profile is 150 VUs. Preparation is staggered as 25, 75, and 150
participants, while all 150 games begin at the supplied epoch. The game phase
uses the UI's 1.2-second polling interval; the following read plateau uses one
poll per VU per second to hold approximately 150 RPS.
