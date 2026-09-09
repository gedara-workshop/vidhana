import SearchApp from "@/components/SearchApp";
import { corpus, facetCounts } from "@/lib/corpus";

/* A server component that reads the corpus at build time and hands it to the
 * workspace, so the index ships in the HTML payload and search works on first
 * keystroke with no round trip. */
export default function Home() {
  return <SearchApp corpus={corpus()} facets={facetCounts()} />;
}
