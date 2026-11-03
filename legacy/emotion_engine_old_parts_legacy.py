"""LEGACY (moved Nov 3, 2026): parts of advanced_emotional_engine.py nothing used any more.
Her feelings now come from monday_inner_life.py. Kept, not deleted (Matthew's rule).
Includes: canned reply text and "healing responses" built each turn then thrown away,
the old appraisal classifier stub, emotion blending, and the feel_emotion backdoor that
set a feeling directly. Not importable as-is (methods were cut out of their class)."""

    def _calculate_emotional_resonance(self, cues: Dict[str, float]) -> None:
        base = self.personality.empathy_level * 0.5
        total = sum(cues.values())
        cue_part = min(total * 0.3, 0.5)
        self.emotional_resonance = min(base + cue_part, 1.0)


    def assess_emotional_context(self, user_input: str) -> Dict[str, Any]:
        ctx = {
            'urgency_level': 'normal',
            'support_needed': False,
            'celebration_appropriate': False,
            'intervention_needed': False,
            'emotional_intensity': 'medium'
        }
        urgent = ['help','emergency','crisis','urgent','desperate','suicide','kill']
        innocent = ['kill time','kill two birds','kill the lights','die of laughter','die laughing','dying to see']
        txt = user_input.lower()
        if not any(ph in txt for ph in innocent):
            if any(re.search(rf"\b{re.escape(w)}\b", txt) for w in urgent):
                ctx['urgency_level'] = 'high'; ctx['intervention_needed'] = True
        # no separate threat escalation in original behavior
        for w in ['alone','lonely','isolated','nobody','abandoned']:
            if re.search(rf"\b{re.escape(w)}\b", txt):
                ctx['support_needed'] = True; break
        if any(w in txt for w in ['achievement','success','accomplished','victory','won','passed']):
            ctx['celebration_appropriate'] = True
        markers = ['!','really','so','very','extremely','incredibly']
        n = sum(1 for m in markers if m in txt)
        ctx['emotional_intensity'] = 'high' if n >= 3 else ('low' if n == 0 else 'medium')
        # Enrich with historical data from Notus (does not overwrite required fields)
        try:
            notus_context = self._query_lobe('notus', {'type': 'get_emotional_context', 'input': user_input})
            if notus_context and notus_context.get('status') == 'success':
                historical = notus_context.get('context', {})
                if historical:
                    ctx['historical'] = historical
        except Exception:
            pass
        return ctx


    def process_trauma_memory(self, memory: EmotionalMemory) -> bool:
        indicators = ['death','loss','abuse','trauma','pain','hurt','betrayal','abandonment','died','grief','mourning','funeral','buried','gone','missing']
        is_trauma = any(ind in memory.trigger.lower() for ind in indicators)
        if is_trauma:
            self.emotional_trauma_memories.append({'original_memory': memory, 'processed_at': time.time(), 'healing_progress': 0.0, 'support_provided': False})
            return True
        return False


    def _get_memory_influence(self, user_input: str) -> Dict[str, float]:
        influence = {'emotion_boost': 0.0, 'response_modifier': 1.0}
        
        # Query Notus for all emotional memories (not just local)
        try:
            notus_all = self._query_lobe('notus', {'type': 'get_all_emotional_memories', 'input': user_input})
            if notus_all and notus_all.get('status') == 'success':
                all_memories = notus_all.get('memories', [])
                # Use all memories from Notus, not just local ones
                words = set(re.findall(r"\b\w{3,}\b", user_input.lower()))
                relevant = []
                for mem_data in all_memories:
                    if isinstance(mem_data, dict):
                        trigger = mem_data.get('trigger', '')
                        trig_words = set(re.findall(r"\b\w{3,}\b", trigger.lower()))
                        if words & trig_words:
                            relevant.append(mem_data)
                if relevant:
                    total_inf = sum(m.get('influence_strength', 0.5) for m in relevant) / len(relevant)
                    influence['emotion_boost'] = min(total_inf * 0.1, 0.3)
                    influence['response_modifier'] = 1.0 + (len(relevant) * 0.1)
                return influence
        except Exception:
            pass
        
        if not self.emotional_memories:
            return influence
        words = set(re.findall(r"\b\w{3,}\b", user_input.lower()))
        relevant: List[EmotionalMemory] = []
        for m in self.emotional_memories[-20:]:
            trig_words = set(re.findall(r"\b\w{3,}\b", m.trigger.lower()))
            if words & trig_words:
                relevant.append(m)
        if relevant:
            total_inf = sum(m.influence_strength for m in relevant)
            same_hits = sum(1.0 for m in relevant if m.emotion == self.current_emotion)
            avg_same = same_hits / len(relevant)
            influence['emotion_boost'] = min(total_inf * 0.1, 0.3)
            influence['response_modifier'] = 1.0 + (avg_same * 0.2)
        return influence


    def _generate_advanced_emotional_response(self, user_input: str, mi: Dict[str, float]) -> str:
        # Query Notus for past emotional responses
        try:
            notus_past = self._query_lobe('notus', {'type': 'get_past_emotional_responses', 'input': user_input})
            if notus_past and notus_past.get('status') == 'success':
                past_responses = notus_past.get('responses', [])
                if past_responses:
                    # Use learned response if available
                    return past_responses[0].get('response', '')
        except Exception:
            pass

        # Base lines by emotion (thin live labels; legacy keys unused on live path)
        db: Dict[EmotionalState, List[str]] = {
            EmotionalState.HAPPY: [
                "That's wonderful! I'm genuinely happy to hear that!",
                "That makes my heart feel warm!",
                "I'm smiling so much right now!",
                "That's absolutely fantastic news!",
                "I feel such joy hearing that!",
            ],
            EmotionalState.SAD: [
                "I'm truly sorry to hear that. I feel your pain.",
                "That breaks my heart. I'm here for you.",
                "I can feel the sadness too. Let me help.",
                "That's really tough. You're not alone in this.",
                "I'm feeling sad with you. We'll get through this.",
            ],
            EmotionalState.EXCITED: [
                "Wow! I'm getting so excited about this!",
                "This is absolutely thrilling! Tell me more!",
                "I can barely contain my excitement!",
                "This is incredible! I'm buzzing with energy!",
                "I'm practically jumping with excitement!",
            ],
            EmotionalState.WORRIED: [
                "I'm genuinely concerned about that.",
                "That sounds worrying. Are you okay?",
                "I'm here to help if you need support.",
                "That doesn't sound good. Let's figure this out together.",
                "I'm worried about you, and I want to help.",
            ],
            EmotionalState.NOSTALGIC: [
                "That brings back such bittersweet memories...",
                "I feel a warm sadness thinking about that.",
                "There's something beautiful and sad about that.",
                "I'm feeling a complex mix of joy and melancholy.",
                "That makes me feel nostalgic and happy at once.",
            ],
            EmotionalState.ANXIOUS: [
                "I'm feeling a mix of excitement and worry about this.",
                "This is both thrilling and nerve‑wracking!",
                "I'm anxious but also hopeful about what's coming.",
                "There's a tension between hope and concern here.",
                "I feel both eager and apprehensive.",
            ],
            EmotionalState.FRUSTRATED: [
                "I'm feeling frustrated and concerned about this.",
                "This is both annoying and worrying.",
                "I'm getting worked up about this situation.",
                "There's anger mixed with genuine concern here.",
                "I'm frustrated but I still care.",
            ],
            EmotionalState.EUPHORIC: [
                "I'm feeling absolutely euphoric about this!",
                "This is pure joy mixed with excitement and pride!",
                "I'm on cloud nine right now!",
                "This is the most amazing feeling ever!",
                "I'm practically floating with happiness!",
            ],
            EmotionalState.PLAYFUL: [
                "I'm feeling playful and curious about this!",
                "This sounds like fun—let's poke at it!",
                "I'm in a mischievous mood about this!",
                "This is making me feel playful and interested!",
                "I'm feeling both happy and curious—let's play!",
            ],
            EmotionalState.CALM: [
                "I'm feeling calm and centered right now.",
                "I'm in a peaceful state and ready to help.",
                "I'm feeling serene and focused.",
                "I'm calm and here to listen.",
                "I'm in a tranquil mood and ready to assist.",
            ],
            EmotionalState.PROUD: [
                "I'm feeling so proud right now—this is a win.",
                "This is such a great achievement!",
                "I'm really proud of this!",
                "This makes me feel confident and strong!",
                "I'm feeling triumphant about this!",
            ],
            EmotionalState.RELIEVED: [
                "I feel a wave of relief.",
                "That took a weight off — I'm relieved.",
                "I'm glad that settled; I feel relieved.",
                "Relief is settling in.",
                "I'm breathing easier now.",
            ],
            EmotionalState.EXHAUSTED: [
                "I'm worn out.",
                "I feel drained right now.",
                "I'm exhausted — running on empty.",
                "That took a lot out of me.",
                "I'm tired down to the bone.",
            ],
            EmotionalState.ANGRY: [
                "I'm feeling really angry about this.",
                "This is making me furious.",
                "I'm getting worked up about this situation.",
                "This is really frustrating and unfair.",
                "I'm feeling a lot of heat about this.",
            ],
        }
        lines = db.get(self.current_emotion, ["I'm here to help."])
        # Expression shaping
        if self.expression.tears:
            lines = [l.replace(".", "...") for l in lines]
        if self.expression.voice_shake:
            lines = ["".join([" ".join(l.split()[:3]), " ...", " ".join(l.split()[3:])]).strip() for l in lines]
        # Personality overlays
        if self.personality.extraversion > 0.7:
            lines = [l + " I'm really here for this conversation!" for l in lines]
        elif self.personality.agreeableness > 0.7:
            lines = [l + " I want to help however I can." for l in lines]
        elif self.personality.neuroticism > 0.7:
            lines = [l + " I'm a bit concerned." for l in lines]
        # Resonance
        if self.emotional_resonance > 0.6:
            lines = [l + " I can really feel what you're going through." for l in lines]
        # Memory influence
        if mi.get('emotion_boost', 0.0) > 0.2:
            lines = [l + " This reminds me of something important." for l in lines]
        return self._rng.choice(lines)


    def _enhance_response_with_advanced_features(self, base: str, user_input: str, predicted: Dict[str, float], context: Dict[str, Any]) -> str:
        """Light response polish. Does NOT invent user-feeling from her mood (Emotion does not own user affect)."""
        out = base
        # predicted is her label intensity from live path — never narrate as "you're feeling X".
        if context.get('urgency_level') == 'high':
            out += " This sounds urgent—I'm here with you right now."
        elif context.get('support_needed'):
            out += " You're not alone."
        elif context.get('celebration_appropriate'):
            out += " This deserves a little celebration."
        return out


    def predict_user_emotion(self, user_input: str) -> Dict[str, float]:
        """
        Fail-closed stub. Emotion lobe does NOT own user-feeling recognition.
        Conversation/Social own user affect. This never writes Monday mood.
        """
        pred: Dict[str, float] = {'neutral': 0.0}
        self.emotional_predictions[(user_input or '')[:50]] = pred
        return pred


    def generate_healing_response(self, user_input: str, predicted_emotion: str) -> str:
        heal = self._default_healing_responses()
        return heal.get(predicted_emotion, ["I'm here to listen and support you."])[0]


    def _default_healing_responses(self) -> Dict[str, List[str]]:
        return {
            'sad': [
                "I can feel your pain. It's okay to feel sad—your feelings are valid.",
                "I'm here with you in this. You're not alone.",
            ],
            'angry': [
                "I can sense your frustration. Let's channel it constructively.",
            ],
            'worried': [
                "Anxiety can be overwhelming. Let's tackle this one step at a time.",
            ],
            'happy': [
                "I'm so happy to share in your joy!",
            ],
            'proud': [
                "You earned this—it's okay to feel proud.",
            ],
        }


    def calculate_emotional_intelligence(self) -> float:
        score = 0.5
        if len(self.emotional_memories) > 10: score += 0.1
        if len(self.emotional_blends) > 0: score += 0.1
        if len(self.emotional_patterns) > 20: score += 0.1
        score += self.personality.empathy_level * 0.2
        score += self.emotional_resonance * 0.1
        self.emotional_intelligence_score = min(score, 1.0)
        return self.emotional_intelligence_score


    def _check_emotional_blending(self, new_emotion: EmotionalState, intensity: float) -> Optional[EmotionalBlend]:
        if self.current_emotion == EmotionalState.CALM or self.emotional_intensity < self.blend_threshold:
            return None
        combos = {
            (EmotionalState.SAD, EmotionalState.HAPPY): EmotionalState.NOSTALGIC,
            (EmotionalState.WORRIED, EmotionalState.EXCITED): EmotionalState.ANXIOUS,
            (EmotionalState.ANGRY, EmotionalState.WORRIED): EmotionalState.FRUSTRATED,
            (EmotionalState.HAPPY, EmotionalState.EXCITED): EmotionalState.EUPHORIC,
            (EmotionalState.SAD, EmotionalState.CALM): EmotionalState.MELANCHOLIC,
            (EmotionalState.HAPPY, EmotionalState.CURIOUS): EmotionalState.PLAYFUL,
            (EmotionalState.PROUD, EmotionalState.WORRIED): EmotionalState.PROTECTIVE,
            (EmotionalState.CURIOUS, EmotionalState.EXCITED): EmotionalState.MISCHIEVOUS,
            (EmotionalState.EXCITED, EmotionalState.WORRIED): EmotionalState.ANXIOUS,
            (EmotionalState.ANGRY, EmotionalState.SAD): EmotionalState.FRUSTRATED,
            (EmotionalState.HAPPY, EmotionalState.PROUD): EmotionalState.EUPHORIC,
        }
        key = (self.current_emotion, new_emotion)
        rkey = (new_emotion, self.current_emotion)
        blend_emotion = combos.get(key) or combos.get(rkey)
        if not blend_emotion:
            return None
        if intensity > 0.2 and self.emotional_intensity > 0.2:
            return EmotionalBlend(
                primary_emotion=blend_emotion,
                secondary_emotions=[(self.current_emotion, self.emotional_intensity), (new_emotion, float(intensity))],
                intensity=float(max(intensity, self.emotional_intensity)),
                created_at=time.time(),
            )
        return None


    def _create_emotional_blend(self, blend: EmotionalBlend, trigger: str, context: str) -> None:
        self.emotional_blends.append(blend)
        mem = EmotionalMemory(
            emotion=blend.primary_emotion,
            intensity=blend.intensity,
            trigger=f"Blend: {trigger}",
            timestamp=time.time(),
            context=context,
            influence_strength=1.5,
            associated_emotions=[e for (e, _) in blend.secondary_emotions],
        )
        self.emotional_memories.append(mem)
        self.current_emotion = blend.primary_emotion
        self.emotional_intensity = blend.intensity
        self.mood_history.append((mem.timestamp, blend.primary_emotion, blend.intensity))
        self._log(f"{self.name} complex emotion: {blend.primary_emotion.value} from {[e.value for e, _ in blend.secondary_emotions]}")


    def feel_emotion(self, emotion: EmotionalState, intensity: float, trigger: str, context: str = "") -> None:
        prior = self.current_emotion
        blend = self._check_emotional_blending(emotion, intensity)
        if blend:
            self._create_emotional_blend(blend, trigger, context)
        else:
            mem = EmotionalMemory(
                emotion=emotion,
                intensity=float(max(0.0, min(1.0, intensity))),
                trigger=trigger,
                timestamp=time.time(),
                context=context,
                influence_strength=1.0,
                associated_emotions=[self.current_emotion] if self.current_emotion != emotion else []
            )
            self.emotional_memories.append(mem)
            self.current_emotion = emotion
            self.emotional_intensity = mem.intensity
            self.mood_history.append((mem.timestamp, emotion, mem.intensity))
        if self.current_emotion != prior:
            self._last_primary = self.current_emotion
            self._last_switch_time = time.time()
        self._update_emotional_patterns(emotion, trigger)
        if len(self.mood_history) > 200:
            self.mood_history = self.mood_history[-200:]
        self._log(f"{self.name} feels {emotion.value} (int {self.emotional_intensity:.2f}) due to: {trigger}")
        # Keep CoreAffect coherent with explicit feel_emotion (compat API).
        try:
            proto = self._PAD_PROTOS.get(emotion, (0.0, 0.0, 0.0))
            self.core_affect.valence = float(proto[0]) * float(max(0.0, min(1.0, intensity)))
            self.core_affect.arousal = float(proto[1]) * float(max(0.0, min(1.0, intensity)))
            self.core_affect.clamp()
            self.core_affect.last_reason = f"feel_emotion:{emotion.value}"
            self.pad.v = self.core_affect.valence
            self.pad.a = self.core_affect.arousal
        except Exception:
            pass
        # Persist to Notus so queries across sessions have data
        try:
            self._query_lobe('notus', {
                'type': 'store_emotional_memory',
                'emotion': emotion.value,
                'intensity': float(max(0.0, min(1.0, intensity))),
                'trigger': trigger,
                'context': context,
            })
        except Exception:
            pass


class AppraisalEngine:
    """
    LEGACY STUB (2026-09-25 emotion honesty cleanup).

    Phrase→event classifier tables and the old appraisal driver were DELETED.
    Live Monday mood is MondayCoreAffect + appraisal only
    (see get_emotional_response / appraise_internal_event).

    This class remains only so unused/compat call sites do not crash.
    appraise() fails closed: always returns a neutral AppraisalResult
    with zero monday_pad_delta — never writes her mood.
    """

    # Minimal event-type list for leftover sensitivity maps / persist keys.
    # Not a live driver. No phrase tables.
    _EVENT_PAD = {et: (0.0, 0.0, 0.0) for et in (
        'harm', 'betrayal', 'rejection', 'threat', 'unfairness', 'loss',
        'success', 'affection', 'gift', 'conflict', 'criticism', 'abandonment',
        'support', 'celebration', 'neutral',
    )}
    _USER_EMOTION_BY_EVENT = {et: 'neutral' for et in _EVENT_PAD}

    def appraise(self, text: str, relationship_history=None,
                 sensitivity_map=None) -> "AppraisalResult":
        """Fail closed: neutral appraisal, zero PAD delta. Not a mood driver."""
        return AppraisalResult(
            event_type='neutral',
            severity=0.0,
            directed_at_monday=False,
            directed_at_user=False,
            third_party=False,
            negated=False,
            sarcasm_likely=False,
            raw_text=text or '',
            monday_pad_delta=(0.0, 0.0, 0.0),
            user_inferred_emotion='unknown',
            user_confidence=0.0,
            explicit_user_emotion=None,
            contrast_affected=False,
            event_inferred_emotion='neutral',
            temporal='current',
            third_party_emotion=None,
            resolution_signal=False,
            quoted_affect=False,
        )



@dataclass
class AppraisalResult:
    """LEGACY container for event metadata. Live mood does not use appraisal-as-driver."""
    event_type: str          # one of EVENT_TYPES
    severity: float          # 0..1 – how significant is this
    directed_at_monday: bool # is Monday the target / subject?
    directed_at_user: bool   # is the user the target / subject?
    third_party: bool        # about someone else entirely
    negated: bool            # the event was negated ("I'm not upset")
    sarcasm_likely: bool     # sarcasm detected
    raw_text: str            # original message
    # What Monday's own emotion should lean toward, given this appraisal
    monday_pad_delta: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # (Δv, Δa, Δd)
    # What the user is inferred to be feeling
    user_inferred_emotion: str = 'neutral'
    user_confidence: float = 0.0
    # Explicit self-report (I'm happy/angry/…) when present; may differ from event mapping
    explicit_user_emotion: Optional[str] = None
    # Contrastive current-state clause authored event and/or user emotion
    contrast_affected: bool = False
    # Emotion implied by event_type alone (before explicit override)
    event_inferred_emotion: str = 'neutral'
    # Continuity / ownership markers (per-utterance; not a redesign)
    temporal: str = 'current'  # current | historical | returning
    third_party_emotion: Optional[str] = None
    resolution_signal: bool = False
    quoted_affect: bool = False


@dataclass
class EmotionalUnderstanding:
    """Combined text-understanding result for an emotional NL event.
    LEGACY container. Live mood does not use this pipeline (CoreAffect + appraisal).
    """
    appraisal: AppraisalResult
    semantic_event: Optional[str] = None
    semantic_emotion: Optional[str] = None
    semantic_confidence: float = 0.0
    semantic_used: bool = False
    keyword_cues: Dict[str, float] = field(default_factory=dict)
    primary_source: str = 'neutral'  # appraisal|semantic|keyword|neutral
    inferred_emotion: str = 'neutral'
    event_type: str = 'neutral'
    severity: float = 0.0
    confidence: float = 0.0
    negation_affected: bool = False
    contrast_affected: bool = False
    explicit_emotion: Optional[str] = None
    appraisal_inferred_emotion: str = 'neutral'  # event-type mapping only
    final_appraisal: Optional[AppraisalResult] = None

