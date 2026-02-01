import google.generativeai as genai
import os
import logging
import json
from typing import Dict, List, Optional

class AIService:
    """Service for AI-powered analysis using Gemini."""
    
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model = None
        self.enabled = False
        
        if self.api_key:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel('gemini-pro')
                self.enabled = True
                logging.info("Gemini AI integration enabled.")
            except Exception as e:
                logging.error(f"Failed to initialize Gemini AI: {e}")
        else:
            logging.info("GEMINI_API_KEY not set. AI features disabled.")

    async def verify_incident(self, node_name: str, metrics: Dict, history: List[Dict]) -> str:
        """
        Ask AI to verify if a suspicious event is a real anomaly.
        Returns: 'CONFIRMED', 'IGNORE', or 'UNCERTAIN'.
        """
        if not self.enabled:
            return "UNCERTAIN"
            
        try:
            # Construct context
            history_summary = self._summarize_history(history)
            
            prompt = f"""
            You are a network monitoring AI. Analyze this potential incident.
            
            Node: {node_name}
            Current State:
            - Speed: {metrics.get('speed', 0)} KB/s
            - Users: {metrics.get('users', 0)}
            - Efficiency: {metrics.get('efficiency', 0)} KB/s/user
            
            Recent History (Last 6 hours):
            {history_summary}
            
            Task:
            Verification: Is this a real performance anomaly or GFW blocking event?
            Normal behavior varies by time of day.
            
            Respond with ONLY one word: CONFIRMED or IGNORE.
            """
            
            response = await self.model.generate_content_async(prompt)
            verdict = response.text.strip().upper()
            
            if "CONFIRMED" in verdict:
                return "CONFIRMED"
            elif "IGNORE" in verdict:
                return "IGNORE"
            else:
                return "UNCERTAIN"
                
        except Exception as e:
            logging.error(f"AI Verification failed: {e}")
            return "UNCERTAIN"

    async def get_smart_thresholds(self, all_nodes_history: Dict[str, List[Dict]]) -> Dict[str, Dict]:
        """
        Batch analysis of ALL nodes to generate dynamic thresholds for the next 6 hours.
        Returns: {node_name: {'min_efficiency': float, 'min_speed': float}}
        """
        if not self.enabled:
            return {}
            
        try:
            # summarize all nodes
            data_summary = ""
            for node, history in all_nodes_history.items():
                if not history:
                    continue
                # Take simple stats
                speeds = [h.get('speed', 0) for h in history]
                effs = [h.get('eff', 0) for h in history]
                if not speeds: continue
                
                avg_speed = sum(speeds)/len(speeds)
                avg_eff = sum(effs)/len(effs)
                data_summary += f"- {node}: AvgSpeed={avg_speed:.1f}, AvgEff={avg_eff:.1f}\n"

            prompt = f"""
            Analyze these server nodes based on their recent 24h performance.
            Generate "Smart Thresholds" for the NEXT 6 HOURS to detect anomalies.
            
            Current Node Stats (24h Avg):
            {data_summary}
            
            Task:
            Return a JSON object with minimum expected thresholds.
            If a node is generally slow, lower the threshold to avoid false positives.
            If a node is high-performance, keep it reasonable.
            
            Format:
            {{
                "NodeName": {{ "min_efficiency": 10.0, "min_speed": 50.0 }},
                ...
            }}
            
            Return ONLY valid JSON.
            """
            
            response = await self.model.generate_content_async(prompt)
            text = response.text.strip()
            # Clean up potential markdown code blocks
            if text.startswith("```json"):
                text = text.replace("```json", "").replace("```", "")
            
            return json.loads(text)
            
        except Exception as e:
            logging.error(f"AI Batch Analysis failed: {e}")
            return {}

    async def analyze_node(self, node_name: str, history: List[Dict]) -> str:
        """
        Generate a natural language analysis of node performance.
        """
        if not self.enabled:
            return "⚠️ AI service is not enabled. Please set GEMINI_API_KEY."
            
        try:
            history_summary = self._summarize_history(history)
            
            prompt = f"""
            Analyze the performance of node '{node_name}' based on its recent history.
            
            Data (Last 24h samples):
            {history_summary}
            
            Identify:
            1. Determining Trend (improving/degrading)
            2. Peak usage times
            3. Any potential anomalies
            
            Keep the response concise (max 3 bullets).
            """
            
            response = await self.model.generate_content_async(prompt)
            return response.text.strip()
            
        except Exception as e:
            logging.error(f"AI Analysis failed: {e}")
            return f"Error analyzing node: {e}"

    def _summarize_history(self, history: List[Dict]) -> str:
        """Helper to format history for LLM prompt."""
        if not history:
            return "No history data availble."
            
        # Downsample to save tokens (take every 10th sample if too many)
        samples = history
        if len(samples) > 50:
            samples = samples[::int(len(samples)/50)]
            
        summary = ""
        for h in samples:
            summary += f"- Time: {h.get('created_at', 'N/A')}, Speed: {h.get('speed', 0)}, Users: {h.get('users', 0)}, Eff: {h.get('eff', 0)}\n"
        return summary
