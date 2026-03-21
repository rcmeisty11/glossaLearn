
import levenstein from 'js-levenshtein';
import { diffChars } from 'diff';
function removeDiactrics(str) {
    const diactrics = /[\u{064B}\u{064C}\u{064D}\u{064E}\u{064F}\u{0650}\u{0651}\u{0652}]/;
    str = str.replace(diactrics, '');
    str = str.replace('أ', 'ا');
    str = str.replace('إ', 'ا');
    return str;
}

const T = {
  bg: "#0e0d0b", surface: "#1a1815", raised: "#211f1a",
  hover: "#2a2722", border: "#302c25", borderL: "#3d372e",
  text: "#c8bfa8", dim: "#8a7f6e", bright: "#efe6d0",
  gold: "#d4a843", goldDim: "#a68432", goldGlow: "rgba(212,168,67,0.10)",
  red: "#c4574a", blue: "#5a8fb4", green: "#6b9c6b",
  purple: "#8b6fa8", teal: "#5a9e94", orange: "#c4864a",
  rose: "#b4697a", cyan: "#5aafb4",
  font: "'EB Garamond',Georgia,serif",
  mono: "'JetBrains Mono',monospace",
  // Font size scale — bump everything up for readability
  xs: 11, sm: 12, md: 14, lg: 16, xl: 24,
};

function Flashcard({ callback, toSay, lastWordsUttered }) {
    console.log(toSay, lastWordsUttered);
    console.log(diffChars(toSay, lastWordsUttered));
    return (
        <div>
            {toSay && <>Produce {toSay}</>}
            <div><button style={{
                padding: "2px 7px", borderRadius: 3, fontSize: 11, fontWeight: 600,
                letterSpacing: .3, cursor: "pointer", fontFamily: T.font,
                background: false ? clr : "transparent",
                color: 'white',
                border: `1px solid ${false ? clr : T.borderL}`,
                opacity: false ? 1 : 0.6,
              }} onClick={callback}>Submit</button></div>

            {lastWordsUttered && <div>You produced {lastWordsUttered}, </div>}
            {lastWordsUttered && <>{diffChars(lastWordsUttered, toSay).map((part) => {
                // green for additions, red for deletions
                // grey for common parts
                const color = part.added ? 'green' :
                    part.removed ? 'red' : 'grey';
                return (
                    <span style={{ color: color }}>{part.value}</span>
                )
            })} (Distance: {levenstein(removeDiactrics(toSay), lastWordsUttered)})</>}
        </div>
    )
}

export default Flashcard;