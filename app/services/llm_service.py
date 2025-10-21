"""
Unified LLM Service - Handles all OpenAI operations
Replaces: llm_services.py, llm_extractor.py
"""
import json
import time
import base64
import re
from typing import Dict, List, Any, Optional, Callable
import openai
from flask import current_app
from app.utils.response import success_response, error_response, iso_timestamp, log_error


class LLMService:
    """Single service for all LLM operations - vision, text extraction, generation"""

    def __init__(self):
        self.client = openai.OpenAI(api_key=current_app.config['OPENAI_API_KEY'])
        self.text_model = current_app.config.get('DEFAULT_LLM_MODEL', 'gpt-4o-mini')
        self.vision_model = 'gpt-4o'
        self.image_model = 'dall-e-3'
        self.confidence_threshold = current_app.config.get('CONFIDENCE_THRESHOLD', 0.75)

    # === IMAGE PROCESSING ===
    def extract_invoice_from_image(
        self,
        image_data: bytes,
        filename: str = None,
        progress_callback: Callable = None
    ) -> Dict[str, Any]:
        """Extract structured invoice data from image using GPT-4V"""
        start_time = time.time()

        try:
            if progress_callback:
                progress_callback(0.1, "Processing image...")

            # Convert to base64
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            image_format = self._detect_image_format(image_data, filename)

            if progress_callback:
                progress_callback(0.3, "Analyzing with AI...")

            # Use vision model for structured extraction
            response = self.client.chat.completions.create(
                model=self.vision_model,
                messages=[
                    {
                        "role": "system",
                        "content": "Extract invoice data as JSON. Return only valid JSON with this structure: {\"invoice_number\": \"\", \"invoice_date\": \"YYYY-MM-DD\", \"total_amount\": 0, \"line_items\": [{\"description\": \"\", \"quantity\": 0, \"unit_price\": 0, \"line_total\": 0}], \"bill_to\": {\"company_name\": \"\", \"address\": \"\"}, \"subtotal\": 0, \"tax_amount\": 0}"
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Extract all invoice data from this image."},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/{image_format};base64,{image_base64}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=2000,
                temperature=0.1
            )

            if progress_callback:
                progress_callback(0.8, "Parsing results...")

            # Parse response
            raw_response = response.choices[0].message.content
            structured_data = self._parse_json_response(raw_response)

            if not structured_data:
                return error_response(
                    'Failed to parse LLM response',
                    raw_response=raw_response
                )

            # Calculate confidence and metrics
            confidence_score = self._calculate_confidence_score(structured_data, image_data)
            processing_time = int((time.time() - start_time) * 1000)

            if progress_callback:
                progress_callback(1.0, "Complete!")

            return success_response(
                structured_data=structured_data,
                confidence_score=confidence_score,
                processing_time_ms=processing_time,
                model_used=self.vision_model,
                image_format=image_format,
                filename=filename,
                extracted_at=iso_timestamp()
            )

        except Exception as e:
            log_error("Image extraction error", e)
            return error_response(
                str(e),
                processing_time_ms=int((time.time() - start_time) * 1000)
            )

    def extract_text_from_image(self, image_data: bytes, filename: str = None) -> Dict[str, Any]:
        """Simple OCR text extraction from image"""
        start_time = time.time()

        try:
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            image_format = self._detect_image_format(image_data, filename)

            response = self.client.chat.completions.create(
                model=self.vision_model,
                messages=[
                    {
                        "role": "system",
                        "content": "Extract ALL text from this image exactly as it appears. Preserve formatting and structure."
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Extract all text from this image."},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/{image_format};base64,{image_base64}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=2000,
                temperature=0.1
            )

            extracted_text = response.choices[0].message.content
            processing_time = int((time.time() - start_time) * 1000)

            return {
                'success': True,
                'extracted_text': extracted_text,
                'processing_time_ms': processing_time,
                'model_used': self.vision_model,
                'filename': filename
            }

        except Exception as e:
            current_app.logger.error(f"Text extraction error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'processing_time_ms': int((time.time() - start_time) * 1000)
            }

    # === TEXT PROCESSING ===
    def analyze_text(
        self,
        text: str,
        analysis_type: str = "general",
        progress_callback: Callable = None
    ) -> Dict[str, Any]:
        """Analyze text content with LLM"""
        start_time = time.time()

        try:
            if progress_callback:
                progress_callback(0.2, f"Starting {analysis_type} analysis...")

            # Build prompt based on analysis type
            if analysis_type == "invoice_extraction":
                prompt = f"Extract structured invoice data from this text as JSON: {text}"
            elif analysis_type == "summary":
                prompt = f"Summarize this text concisely: {text}"
            elif analysis_type == "validation":
                prompt = f"Validate and flag any issues in this data: {text}"
            else:
                prompt = f"Analyze this text: {text}"

            if progress_callback:
                progress_callback(0.5, "Processing with AI...")

            response = self.client.chat.completions.create(
                model=self.text_model,
                messages=[
                    {"role": "system", "content": "You are an expert text analyst. Provide clear, structured responses."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1500,
                temperature=0.3
            )

            result_text = response.choices[0].message.content
            processing_time = int((time.time() - start_time) * 1000)

            if progress_callback:
                progress_callback(1.0, "Analysis complete!")

            # Try to parse as JSON if it looks like structured data
            structured_result = self._parse_json_response(result_text)

            return {
                'success': True,
                'analysis_type': analysis_type,
                'result_text': result_text,
                'structured_result': structured_result,
                'processing_time_ms': processing_time,
                'model_used': self.text_model
            }

        except Exception as e:
            current_app.logger.error(f"Text analysis error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'processing_time_ms': int((time.time() - start_time) * 1000)
            }

    # === IMAGE GENERATION ===

    def generate_invoice_image(
        self,
        business_type: str = "general",
        complexity: str = "detailed",
        company_name: str = None,
    ) -> Dict[str, Any]:
        """Generate example invoice images using DALL-E"""
        start_time = time.time()

        try:
            prompt = self._build_invoice_prompt(business_type, complexity, company_name)

            response = self.client.images.generate(
                model=self.image_model,
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1
            )

            processing_time = int((time.time() - start_time) * 1000)
            image_url = response.data[0].url

            return {
                'success': True,
                'image_url': image_url,
                'prompt_used': prompt,
                'business_type': business_type,
                'processing_time_ms': processing_time,
                'model_used': self.image_model
            }

        except Exception as e:
            current_app.logger.error(f"Image generation error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'processing_time_ms': int((time.time() - start_time) * 1000)
            }

    # === HELPER METHODS ===

    def _detect_image_format(self, image_data: bytes, filename: str = None) -> str:
        """Detect image format from data or filename"""
        if image_data.startswith(b'\xff\xd8\xff'):
            return 'jpeg'
        elif image_data.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'png'
        elif image_data.startswith(b'GIF'):
            return 'gif'
        elif image_data.startswith(b'RIFF') and b'WEBP' in image_data[:12]:
            return 'webp'

        # Fallback to filename
        if filename:
            ext = filename.lower().split('.')[-1]
            if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                return 'jpeg' if ext == 'jpg' else ext

        return 'jpeg'  # Safe default

    def _parse_json_response(self, response_text: str) -> Optional[Dict]:
        """Parse JSON from LLM response, handling various formats"""
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass

            # Try to find JSON-like content
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    pass

            return None

    def _calculate_confidence_score(self, structured_data: Dict, image_data: bytes) -> float:
        """Calculate confidence score for extraction"""
        base_score = 0.7

        # Check for key invoice fields
        required_fields = ['invoice_number', 'total_amount']
        found_fields = sum(1 for field in required_fields if structured_data.get(field))
        field_score = (found_fields / len(required_fields)) * 0.2

        # Check for line items
        line_items = structured_data.get('line_items', [])
        if line_items and len(line_items) > 0:
            base_score += 0.1

        # Check for financial consistency
        try:
            total = float(structured_data.get('total_amount', 0))
            subtotal = float(structured_data.get('subtotal', 0))
            tax = float(structured_data.get('tax_amount', 0))

            if abs((subtotal + tax) - total) < 1.0:  # Within $1
                base_score += 0.1
        except (ValueError, TypeError):
            pass

        final_score = min(1.0, max(0.0, base_score + field_score))
        return final_score

    def _build_invoice_prompt(self, business_type: str, complexity: str, company_name: str) -> str:
        """Build prompt for invoice image generation"""
        if not company_name:
            company_name = f"Sample {business_type.replace('_', ' ').title()} Co"

        return f"""Create a realistic business invoice for {company_name}, a {business_type.replace('_', ' ')} business.

Include: invoice number, dates, bill-to address, itemized products/services, quantities, prices, subtotal, tax, total.
Complexity: {complexity} - {'3-5 items' if complexity == 'simple' else '8-12 items' if complexity == 'detailed' else '15+ items'}
Style: Professional, clean, black text on white background, typical business invoice format."""

    # === SUPPORTED FORMATS ===

    def get_supported_image_formats(self) -> List[str]:
        """Get supported image formats"""
        return ['jpeg', 'jpg', 'png', 'gif', 'webp']

    def get_supported_business_types(self) -> List[Dict[str, str]]:
        """Get supported business types for image generation"""
        return [
            {"type": "retail", "name": "Retail Store"},
            {"type": "restaurant", "name": "Restaurant"},
            {"type": "consulting", "name": "Consulting Services"},
            {"type": "manufacturing", "name": "Manufacturing"},
            {"type": "technology", "name": "Technology Services"}
        ]


# Singleton pattern for LLM service
_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Get singleton LLM service instance"""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
