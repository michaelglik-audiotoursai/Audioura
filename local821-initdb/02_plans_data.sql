--
-- PostgreSQL database dump
--

\restrict qGflxwijKpm5bugZpx7pU6vgwb1AzgymkNIz3Ft2RFjarMZICKBPS7ulceRiXd5

-- Dumped from database version 15.18
-- Dumped by pg_dump version 15.18

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: plans; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.plans (plan_id, tours_per_day, tour_max_poi, tour_max_minutes, news_per_period, news_period, news_max_minutes, downloads_unlimited, created_at, tours_per_month, fresh_per_pack, edits_per_pack, ops_per_pack, max_stops, max_new_stops_per_edit, by_reference_only, referrals_allowed, referral_period, seat_cap, can_sell, price_usd, inactivity_days, display_name, hidden, article_char_limit) FROM stdin;
free	10	30	120	10	week	10	t	2026-07-21 19:10:45.919597	\N	\N	\N	\N	\N	\N	f	0	\N	\N	f	0.00	\N	\N	t	5000
ppu	999	50	300	999	day	60	t	2026-07-31 19:11:35.828432	\N	\N	\N	\N	\N	\N	f	0	\N	\N	f	0.00	\N	\N	t	5000
unlimited	999	50	300	999	day	60	t	2026-07-31 19:11:35.830239	\N	\N	\N	\N	\N	\N	f	0	\N	\N	f	0.00	\N	\N	t	5000
l1	0	0	120	10	month	10	t	2026-10-06 19:07:01.639788	0	0	0	0	0	0	f	0	\N	\N	f	0.00	\N	Introduction	f	5000
l2	1	5	120	10	month	10	t	2026-10-06 19:07:01.639788	3	\N	\N	\N	5	0	t	0	\N	100	t	0.00	7	Free	f	5000
l3	999	10	300	999	month	60	t	2026-10-06 19:07:01.639788	\N	5	5	\N	10	10	f	3	lifetime	\N	t	10.00	\N	$10 Pack	f	10000
l4	999	25	300	999	month	60	t	2026-10-06 19:07:01.639788	\N	\N	\N	25	25	10	f	5	month	\N	t	25.00	\N	Curator	f	15000
admin	999	50	300	999	day	60	t	2026-10-06 20:14:08.570032	\N	\N	\N	\N	50	50	f	0	lifetime	\N	t	0.00	\N	Administrator	t	15000
tester	10	5	300	999	month	60	t	2026-10-06 19:07:01.639788	50	\N	\N	\N	5	5	f	3	month	\N	t	0.00	\N	Tester	t	15000
\.


--
-- PostgreSQL database dump complete
--

\unrestrict qGflxwijKpm5bugZpx7pU6vgwb1AzgymkNIz3Ft2RFjarMZICKBPS7ulceRiXd5

