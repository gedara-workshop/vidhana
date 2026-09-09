import SearchApp from "@/components/SearchApp";
import { corpus, facetCounts } from "@/lib/corpus";

/* The search page. A server component that reads the corpus at build time and
 * hands it to one client island — so the index ships as part of the HTML
 * payload and search works on first interaction, with no round trip. */
export default function Home() {
  return <SearchApp corpus={corpus()} facets={facetCounts()} />;
}
