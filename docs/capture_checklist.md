# Capture checklist

One box per page: **90 pages** (30 airlines x 3 page types).
How to capture each page: see [capture_guide.md](capture_guide.md).

The URLs were **suggested by web search** on 2026-11-11 and are **not checked yet**
(`url_verified = no` in `data/airlines.csv`). For every page:

1. Open the suggested URL in your capture browser profile.
2. Check it is the right page, in English, for the right country (see the note).
   - Wrong or outdated? Find the right page by clicking through the site
     (no logins, no typing into forms) and **correct the URL in `data/airlines.csv`**.
   - `MISSING` = web search did not find it. Look for it on the site for up to
     about 5 minutes. If the airline really has no such page, leave `MISSING`.
3. Capture it with SingleFile, rename it, add the row to `data/captures/log.csv`.
4. Tick the box.

When all three pages of an airline are checked, set **`url_verified` to `yes`** for that
airline in `data/airlines.csv`. (The live scanner only scans airlines marked `yes`.)

**6 pages are MISSING** and **64 have a note** to check.

## India


### Air India (`air_india`)

- [x] **home**: <https://www.airindia.com>  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
- [x] **checkin**: <https://www.airindia.com/in/en/manage/web-checkin.html>
- [x] **assistance**: <https://www.airindia.com/in/en/travel-information/health-medical-assistance/disability-assistance.html>

### IndiGo (`indigo`)

- [x] **home**: <https://www.goindigo.in>  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
- [x] **checkin**: <https://www.goindigo.in/web-check-in.html>
- [x] **assistance**: <https://www.goindigo.in/information/special-disability-assistance.html>

### SpiceJet (`spicejet`)

- [x] **home**: <https://www.spicejet.com>  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
- [x] **checkin**: <https://www.spicejet.com/checkin>  
  _Update 2026-11-11: redirects to the homepage (#checkin) -> SAME_AS_HOME in airlines.csv; not scanned separately_
- [ ] **assistance**: <https://spicejet.com/SpecialAssistance.aspx>    
  _Update 2026-11-11: this URL redirected to the homepage; now MISSING in airlines.csv (to be confirmed)_
  _Note: old-style .aspx page; SpiceJet's site has several old versions (classic/corporate) - look for a current page on spicejet.com_

### Akasa Air (`akasa_air`)

- [x] **home**: <https://www.akasaair.com>  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
- [x] **checkin**: <https://www.akasaair.com/check-in/web-check-in>
- [ ] **assistance**: MISSING  
  _Note: no assistance page found; assistance rules are only a section of the Conditions of Carriage (https://www.akasaair.com/quick-links/conditions-of-carriage) - look for a real page on the site_

### Air India Express (`air_india_express`)

- [x] **home**: <https://www.airindiaexpress.com>  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
- [x] **checkin**: <https://www.airindiaexpress.com/checkin-home>
- [ ] **assistance**: MISSING  
  _Note: no assistance page found (the 'specialequipment' page is for sports equipment) - look on the site_

## Japan/Asia


### ANA (`ana`)

- [x] **home**: <https://www.ana.co.jp/en/jp/>
- [x] **checkin**: <https://aswbe-i.ana.co.jp/international_asw/pages/webcheckin/checkin_search_input.xhtml?CONNECTION_KIND=CHE&LANG=en>  
  _Note: separate booking-engine site (aswbe-i.ana.co.jp); ANA's info page is https://www.ana.co.jp/en/jp/guide/boarding-procedures/checkin/international/online-checkin/_
- [x] **assistance**: <https://www.ana.co.jp/en/jp/guide/flight_service_info/assist/>

### JAL (`jal`)

- [x] **home**: <https://www.jal.co.jp/jp/en/>
- [x] **checkin**: <https://www.jal.co.jp/jp/en/inter/boarding/online-checkin/>
- [x] **assistance**: <https://www.jal.co.jp/jp/en/jalpri/support/>

### Peach (`peach`)

- [x] **home**: <https://www.flypeach.com/en>
- [ ] **checkin**: MISSING  
  _Note: web check-in is app-only; no Manage Booking URL found - look for 'Manage Booking' on the homepage_
- [x] **assistance**: <https://www.flypeach.com/en/lm/ai/airports/special_support>

### Singapore Airlines (`singapore_airlines`)

- [x] **home**: <https://www.singaporeair.com>  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
- [x] **checkin**: <https://www.singaporeair.com/en_UK/sg/travel-info/check-in/online-mobile-checkin/>  
  _Note: may be an info page - check that it has the booking-reference form_
- [x] **assistance**: <https://www.singaporeair.com/en_UK/us/travel-info/special-assistance/>  
  _Note: US-market version (en_UK/us) - switch to Singapore (sg) if it exists_

### Cathay Pacific (`cathay_pacific`)

- [x] **home**: <https://www.cathaypacific.com>  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
- [ ] **checkin**: MISSING  
  _Note: only FAQ pages found - look for 'Manage booking' / 'Check in' on the homepage_
- [x] **assistance**: <https://www.cathaypacific.com/cx/en_US/prepare-trip/help-for-passengers.html>  
  _Note: US-market version (en_US) - switch to Hong Kong (en_HK) if it exists_

## Europe


### Lufthansa (`lufthansa`)

- [x] **home**: <https://www.lufthansa.com>  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
- [x] **checkin**: <https://www.lufthansa.com/ge/en/online-check-in>  
  _Note: Georgia-market version (/ge/en/) - switch to Germany (/de/en/) if it exists_
- [x] **assistance**: <https://www.lufthansa.com/hk/en/travellers-with-special-needs.html>  
  _Note: Hong Kong-market version (/hk/en/) - switch to Germany (/de/en/) if it exists_

### Air France (`air_france`)

- [x] **home**: <https://www.airfrance.com>  
  _Update 2026-11-11: captured as https://wwws.airfrance.fr/en (replacement for the splash page)_  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
- [x] **checkin**: <https://wwws.airfrance.co.uk/check-in>  
  _Note: UK-market version (airfrance.co.uk) - switch to France/English if it exists_
- [x] **assistance**: <https://wwws.airfrance.fr/en/information/passagers/acheter-billet-avion-pmr-autres-handicaps>

### KLM (`klm`)

- [x] **home**: <https://www.klm.com>  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
- [x] **checkin**: <https://www.klm.nl/en/check-in>
- [x] **assistance**: <https://www.klm.com/information/assistance-health>  
  _Note: US-market version - switch to Netherlands/English if it exists_

### Ryanair (`ryanair`)

- [x] **home**: <https://www.ryanair.com>  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
- [x] **checkin**: <https://www.ryanair.com/us/en/lp/check-in/link?returnTo=managehub>  
  _Note: booking-lookup page found ('Lost Booking' title) - check it is the check-in start page_
- [x] **assistance**: <https://help.ryanair.com/hc/en-us/categories/12489466690833-Special-Assistance>  
  _Note: separate help-centre site (help.ryanair.com)_

### easyJet (`easyjet`)

- [x] **home**: <https://www.easyjet.com>  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
- [x] **checkin**: <https://www.easyjet.com/en/help/booking-and-check-in/check-in>  
  _Note: help page about check-in; not the check-in form (check-in is inside Manage Bookings which needs login - do NOT log in; use the 'Find booking' form if there is one)_
- [x] **assistance**: <https://www.easyjet.com/en/help/boarding-and-flying/special-assistance>

### Iberia (`iberia`)

- [x] **home**: <https://www.iberia.com>  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
- [x] **checkin**: <https://www.iberia.com/us/checkin-information/>  
  _Note: info page; US-market version - check for the booking-reference form; switch to Spain/English if it exists_
- [x] **assistance**: <https://www.iberia.com/us/fly-with-iberia/special-needs/>  
  _Note: US-market version - switch to Spain/English if it exists_

### Finnair (`finnair`)

- [x] **home**: <https://www.finnair.com>  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
  _Update 2026-11-11: re-captured as https://www.finnair.com/fi-en (first capture was only the country-selection page)_
- [x] **checkin**: <https://www.finnair.com/fi-en/check-in>
- [x] **assistance**: <https://www.finnair.com/us-en/special-assistance-and-health>  
  _Note: US-market version (us-en) - switch to Finland (fi-en) if it exists_

### SAS (`sas`)

- [x] **home**: <https://www.flysas.com>  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
- [x] **checkin**: <https://www.flysas.com/us-en/checkin>  
  _Note: US-market version (us-en)_
- [x] **assistance**: <https://www.flysas.com/nl-en/travel-info/assistance/>  
  _Note: Netherlands-market version (nl-en)_

### TAP Air Portugal (`tap_air_portugal`)

- [x] **home**: <https://www.flytap.com>  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
- [x] **checkin**: <https://www.flytap.com/en-us/check-in/online-check-in>  
  _Note: US-market version (en-us) - switch to Portugal/English if it exists_
- [x] **assistance**: <https://www.flytap.com/en-us/special-needs>  
  _Note: US-market version (en-us) - switch to Portugal/English if it exists_

### Turkish Airlines (`turkish_airlines`)

- [x] **home**: <https://www.turkishairlines.com>  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
- [x] **checkin**: <https://www.turkishairlines.com/en-int/flights/check-in/oci-select-seats/selectseatocitys.html>  
  _Update 2026-11-11: redirects to the homepage -> SAME_AS_HOME in airlines.csv; not scanned separately_
  _Note: unusual URL (seat-selection path) - check it opens the check-in start page; info page is https://www.turkishairlines.com/en-us/any-questions/check-in/_
- [x] **assistance**: <https://www.turkishairlines.com/en-int/any-questions/special-assistance-for-passengers/>

## North America


### Delta (`delta`)

- [x] **home**: <https://www.delta.com>  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
- [x] **checkin**: <https://www.delta.com/PCCOciWeb/findBy.action>  
  _Note: older check-in application URL - check it still works; overview is https://www.delta.com/us/en/check-in-security/overview_
- [x] **assistance**: <https://www.delta.com/us/en/accessible-travel-services/additional-assistance>  
  _Note: sub-page ('Airport & Onboard Assistance') - look for an accessible-travel overview page_

### United (`united`)

- [x] **home**: <https://www.united.com>  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
- [x] **checkin**: <https://www.united.com/en/NG/checkin>  
  _Note: Nigeria-market version (/en/NG/) - switch to US (/en/us/)_
- [ ] **assistance**: MISSING  
  _Note: only found on a preview server (gtmpreview.united.com) - not used; look for 'Customers with disabilities' on united.com_

### American (`american`)

- [x] **home**: <https://www.aa.com>  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
- [x] **checkin**: <https://www.aa.com/reservation/flightCheckInViewReservationsAccess.do>
- [x] **assistance**: <https://www.aa.com/web/i18n/travel-info/special-assistance/special-assistance.html>

### Southwest (`southwest`)

- [x] **home**: <https://www.southwest.com>  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
- [x] **checkin**: <https://www.southwest.com/air/check-in/>
- [x] **assistance**: <https://support.southwest.com/helpcenter/s/pathway/a1F5G00000cLOqhUAG/disabilityrelated-accommodations>  
  _Note: separate help-centre site (support.southwest.com)_

### Alaska (`alaska`)

**EXCLUDED (blocked_for_human_visitor)**: on 2026-11-11 none of the 3 pages loaded in a normal
browser (blocked or error), so there are no captures. Alaska stays in the results, marked as excluded
(`excluded_reason` in data/airlines.csv and data/results/automated_access.csv).

- [ ] **home**: <https://www.alaskaair.com>  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
- [ ] **checkin**: <https://www.alaskaair.com/content/travel-info/at-the-airport/airport-check-in-options>  
  _Note: info page about check-in options - check for the actual check-in form_
- [ ] **assistance**: <https://www.alaskaair.com/content/travel-info/accessible-services/specialservices-tsa>  
  _Note: sub-page (seating) of the 'accessible services' section - look for the section's overview page_

### JetBlue (`jetblue`)

- [x] **home**: <https://www.jetblue.com>  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
- [x] **checkin**: <https://mobilecheckin.jetblue.com/>  
  _Note: separate check-in site (mobilecheckin.jetblue.com)_
- [x] **assistance**: <https://www.jetblue.com/at-the-airport/accessibility-assistance>

### Air Canada (`air_canada`)

- [x] **home**: <https://www.aircanada.com>  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
- [x] **checkin**: <https://www.aircanada.com/home/ca/en/aco/checkin>
- [ ] **assistance**: MISSING  
  _Note: no assistance page found; only the Accessibility Plan and FAQ - look for 'Accessibility' / 'Special assistance' on the site_

## Middle East/Oceania


### Emirates (`emirates`)

- [ ] **home**: <https://www.emirates.com>  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
- [ ] **checkin**: <https://www.emirates.com/ae/english/manage-booking/online-check-in/>  
  _Note: UAE (ae/english) version_
- [ ] **assistance**: <https://www.emirates.com/ae/english/help/accessibility-hub/accessible-travel/>

### Qatar Airways (`qatar_airways`)

- [ ] **home**: <https://www.qatarairways.com/en-qa/homepage.html>
- [ ] **checkin**: <https://www.qatarairways.com/en-us/services-checking-in.html>  
  _Note: US-market version (en-us) - switch to Qatar (en-qa) if it exists_
- [ ] **assistance**: <https://www.qatarairways.com/en/services-special/disability-and-medical.html>  
  _Note: generic English version (/en/)_

### Qantas (`qantas`)

- [ ] **home**: <https://www.qantas.com>  
  _Note: bare domain: the site redirects by location - choose English and the airline's home country_
- [ ] **checkin**: <https://www.qantas.com/en-us/manage-booking/check-in>  
  _Note: US-market version (en-us) - switch to Australia (en-au) if it exists_
- [ ] **assistance**: <https://www.qantas.com/en-us/travel-information/specific-needs-assistance>  
  _Note: US-market version (en-us) - switch to Australia (en-au) if it exists_
