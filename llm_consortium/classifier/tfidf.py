"""
Pure Python TF-IDF classifier — no sklearn dependency.
Uses cosine similarity against category centroid vectors.
"""
import re, math
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

TRAINING_EXAMPLES = {
    "coding": [
        "write a python function to sort a list", "debug this javascript error in my react component",
        "create a sql query to find duplicate records", "how to implement binary search in python",
        "fix the null pointer exception in java", "deploy docker container to kubernetes",
        "write unit tests with pytest", "optimize this algorithm for better time complexity",
        "create a rest api endpoint with fastapi", "parse json data and extract nested fields",
    ],
    "math": [
        "calculate the derivative of x squared plus 3x", "solve the equation 2x plus 5 equals 15",
        "what is 15 percent of 240", "find the eigenvalues of this matrix",
        "prove this theorem about prime numbers", "compute the integral of sine x",
        "what is the probability of rolling two sixes", "simplify this algebraic expression",
        "find the area of a circle with radius 5", "solve this system of linear equations",
    ],
    "reasoning": [
        "analyze the trade-offs between microservices and monoliths", "compare and contrast rest and graphql apis",
        "what are the pros and cons of remote work", "if all roses are flowers and some flowers fade quickly do all roses fade quickly",
        "what are the implications of artificial intelligence on society", "develop a strategy for entering a new market",
        "evaluate the ethical considerations of data privacy", "what logical fallacy is present in this argument",
        "deduce the conclusion from these premises", "what are the advantages and disadvantages of nuclear energy",
    ],
    "creative": [
        "write a story about a time traveler", "compose a poem about the ocean",
        "create a dialogue between two strangers meeting on a train", "write a haiku about autumn",
        "imagine a world where gravity works differently", "craft a compelling character backstory",
        "write a song about lost love", "generate ideas for a science fiction novel",
        "describe a bustling marketplace scene", "write a short essay about the meaning of friendship",
    ],
    "sysadmin": [
        "how to configure nginx as a reverse proxy", "set up a cron job to run backups daily",
        "configure iptables firewall rules", "troubleshoot systemd service failure",
        "mount a network drive on linux", "set up ssh key authentication",
        "configure dns records for a domain", "debug permission denied error with chmod",
        "install packages with apt on ubuntu", "set up environment variables in bash",
    ],
    "factual": [
        "what is the capital of france", "who invented the telephone",
        "when did world war 2 end", "where is the great wall of china",
        "what is photosynthesis", "who wrote romeo and juliet",
        "what year did the berlin wall fall", "explain how the immune system works",
        "what is the meaning of life", "list the types of clouds in meteorology",
    ],
}

STOP_WORDS = frozenset({
    'a','an','the','is','are','was','were','be','been','being','have','has','had',
    'do','does','did','will','would','could','should','may','might','must','shall',
    'can','to','of','in','for','on','with','at','by','from','as','into','through',
    'during','before','after','above','below','up','down','out','off','over','under',
    'then','once','here','there','when','where','why','how','all','each','every',
    'both','few','more','most','other','some','such','no','nor','not','only','own',
    'same','so','than','too','very','just','i','me','my','we','our','you','your',
    'he','him','his','she','her','it','its','they','them','their','this','that',
    'these','those','and','or','but','if',
})

def tokenize(text: str) -> List[str]:
    text = text.lower()
    tokens = re.findall(r'\b[a-z][a-z0-9+#]*\b', text)
    return [t for t in tokens if t not in STOP_WORDS and len(t) > 1]

class TFIDFClassifier:
    def __init__(self, training_data: Dict[str, List[str]] = None):
        self.training_data = training_data or TRAINING_EXAMPLES
        self._idf: Dict[str, float] = {}
        self._category_vectors: Dict[str, Dict[str, float]] = {}
        self._category_norms: Dict[str, float] = {}
        self._train()

    def _train(self):
        doc_freq = defaultdict(int)
        total_docs = 0
        for category, examples in self.training_data.items():
            seen = set()
            for ex in examples:
                seen.update(tokenize(ex))
                total_docs += 1
            for term in seen:
                doc_freq[term] += 1
        for term, df in doc_freq.items():
            self._idf[term] = math.log((total_docs + 1) / (df + 1)) + 1
        for category, examples in self.training_data.items():
            centroid = defaultdict(float)
            for ex in examples:
                tf = Counter(tokenize(ex))
                doc_len = len(tokenize(ex)) or 1
                for term, count in tf.items():
                    centroid[term] += (count / doc_len) * self._idf.get(term, 1.0)
            n = len(examples) or 1
            for term in centroid:
                centroid[term] /= n
            norm = math.sqrt(sum(v * v for v in centroid.values())) or 1.0
            self._category_vectors[category] = dict(centroid)
            self._category_norms[category] = norm

    def classify(self, text: str) -> dict:
        tokens = tokenize(text)
        tf = Counter(tokens)
        doc_len = len(tokens) or 1
        query_vec = {}
        for term, count in tf.items():
            query_vec[term] = (count / doc_len) * self._idf.get(term, 1.0)
        query_norm = math.sqrt(sum(v * v for v in query_vec.values())) or 1.0
        scores = {}
        for category, cat_vec in self._category_vectors.items():
            cat_norm = self._category_norms[category]
            if query_norm == 0 or cat_norm == 0:
                scores[category] = 0.0
                continue
            dot = sum(query_vec.get(t, 0) * v for t, v in cat_vec.items() if t in query_vec)
            scores[category] = dot / (query_norm * cat_norm)
        if not scores or max(scores.values()) == 0:
            return {"category": "general", "confidence": 0.0, "method": "tfidf", "scores": scores}
        best_category = max(scores, key=scores.get)
        best_score = scores[best_category]
        sorted_scores = sorted(scores.values(), reverse=True)
        if len(sorted_scores) > 1 and sorted_scores[1] > 0:
            confidence = best_score / (best_score + sorted_scores[1])
        else:
            confidence = min(best_score * 2, 1.0)
        return {"category": best_category, "confidence": round(confidence, 3), "method": "tfidf",
                "scores": {k: round(v, 4) for k, v in scores.items()}}
