"use client";

import React, { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import DOMPurify from "dompurify";
import api from "@/lib/api";
import type { ReviewSession, ReviewComment } from "@/types";
import { Button } from "@/components/ui/button";
import { MessageSquare, Loader2, Send, Star, ThumbsUp, ThumbsDown, Minus, CheckCircle } from "lucide-react";

const SENTIMENT_ICONS: Record<string, React.ReactNode> = {
  positive: <ThumbsUp className="h-4 w-4 text-green-500" />,
  negative: <ThumbsDown className="h-4 w-4 text-red-500" />,
  neutral: <Minus className="h-4 w-4 text-gray-500" />,
};

export default function PublicReviewPage() {
  const params = useParams();
  const token = params.token as string;

  const [session, setSession] = useState<ReviewSession | null>(null);
  const [comments, setComments] = useState<ReviewComment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Comment form
  const [reviewerName, setReviewerName] = useState("");
  const [reviewerEmail, setReviewerEmail] = useState("");
  const [section, setSection] = useState("");
  const [commentText, setCommentText] = useState("");
  const [rating, setRating] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    if (token) loadSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const loadSession = async () => {
    setLoading(true);
    try {
      const s = await api.review.getByToken(token);
      setSession(s);
      if (s?.id) {
        const c = await api.review.getComments(s.id);
        setComments(c || []);
      }
    } catch (e: any) {
      setError(e.message || "Review session not found or expired");
    } finally {
      setLoading(false);
    }
  };

  const submitComment = async () => {
    if (!session || !commentText.trim()) return;
    setSubmitting(true);
    try {
      await api.review.addComment(session.id, {
        reviewer_name: reviewerName || "Anonymous",
        comment_text: commentText,
        section: section || "general",
      });
      setCommentText("");
      setRating(0);
      setSection("");
      setSubmitted(true);
      // Reload comments
      const c = await api.review.getComments(session.id);
      setComments(c || []);
      setTimeout(() => setSubmitted(false), 3000);
    } catch (e: any) {
      setError(e.message || "Failed to submit");
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !session) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center space-y-3 p-8">
          <MessageSquare className="h-16 w-16 mx-auto text-muted-foreground/30" />
          <h1 className="text-2xl font-bold">Review Not Found</h1>
          <p className="text-muted-foreground">{error || "This review link may have expired or been deactivated."}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b bg-muted/30">
        <div className="max-w-3xl mx-auto p-6 space-y-2">
          <div className="flex items-center gap-2 text-primary">
            <MessageSquare className="h-5 w-5" />
            <span className="text-sm font-medium">HireStack AI — Document Review</span>
          </div>
          <h1 className="text-2xl font-bold">{session.document_type ? `${session.document_type} Review` : "Document Review"}</h1>
          <p className="text-sm text-muted-foreground">
            Share your feedback on this document. Your comments help improve it.
          </p>
        </div>
      </div>

      <div className="max-w-3xl mx-auto p-6 space-y-8">
        {/* Document Preview */}
        {(session as any).document_snapshot && (
          <div className="rounded-xl border p-6 bg-white dark:bg-zinc-950 max-h-96 overflow-y-auto">
            <div className="prose prose-sm dark:prose-invert max-w-none" dangerouslySetInnerHTML={{
              __html: typeof (session as any).document_snapshot === "string" ? DOMPurify.sanitize((session as any).document_snapshot) : ""
            }} />
          </div>
        )}

        {/* Existing Comments */}
        {comments.length > 0 && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Feedback ({comments.length})</h2>
            <div className="space-y-3">
              {comments.map((c, i) => (
                <div key={i} className="rounded-lg border p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm">{c.reviewer_name || "Anonymous"}</span>
                      {c.section && <span className="text-xs bg-muted px-2 py-0.5 rounded">{c.section}</span>}
                    </div>
                    <div className="flex items-center gap-2">
                      {c.sentiment && SENTIMENT_ICONS[c.sentiment]}
                      {(c as any).rating && (
                        <div className="flex items-center gap-0.5">
                          {Array.from({ length: 5 }).map((_, si) => (
                            <Star key={si} className={`h-3 w-3 ${si < (c as any).rating ? "fill-yellow-500 text-yellow-500" : "text-muted"}`} />
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                  <p className="text-sm text-muted-foreground">{c.comment_text}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Submit Comment */}
        <div className="rounded-xl border p-6 space-y-4">
          <h2 className="text-lg font-semibold">Add Your Feedback</h2>

          {submitted && (
            <div className="flex items-center gap-2 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg text-green-700 dark:text-green-300">
              <CheckCircle className="h-4 w-4" />
              <span className="text-sm font-medium">Thank you! Your feedback has been submitted.</span>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <label htmlFor="reviewer-name" className="text-sm font-medium">Your Name</label>
              <input
                id="reviewer-name"
                className="w-full rounded-lg border bg-background p-3 text-sm"
                placeholder="Anonymous"
                value={reviewerName}
                onChange={(e) => setReviewerName(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="reviewer-email" className="text-sm font-medium">Email (optional)</label>
              <input
                id="reviewer-email"
                className="w-full rounded-lg border bg-background p-3 text-sm"
                placeholder="your@email.com"
                type="email"
                value={reviewerEmail}
                onChange={(e) => setReviewerEmail(e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-2">
            <label htmlFor="review-section" className="text-sm font-medium">Section</label>
            <select
              id="review-section"
              className="w-full rounded-lg border bg-background p-3 text-sm"
              value={section}
              onChange={(e) => setSection(e.target.value)}
            >
              <option value="">General</option>
              <option value="header">Header / Contact Info</option>
              <option value="summary">Professional Summary</option>
              <option value="experience">Experience</option>
              <option value="education">Education</option>
              <option value="skills">Skills</option>
              <option value="formatting">Formatting / Layout</option>
              <option value="tone">Tone / Language</option>
            </select>
          </div>

          {/* Star Rating */}
          <div className="space-y-2">
            <label id="review-rating-label" className="text-sm font-medium">Rating</label>
            <div className="flex items-center gap-1" role="group" aria-labelledby="review-rating-label">
              {[1, 2, 3, 4, 5].map((n) => (
                <button key={n} onClick={() => setRating(n === rating ? 0 : n)} className="p-1">
                  <Star className={`h-6 w-6 transition-colors ${n <= rating ? "fill-yellow-500 text-yellow-500" : "text-muted hover:text-yellow-400"}`} />
                </button>
              ))}
              {rating > 0 && <span className="text-sm text-muted-foreground ml-2">{rating}/5</span>}
            </div>
          </div>

          <div className="space-y-2">
            <label htmlFor="review-comment" className="text-sm font-medium">Comment *</label>
            <textarea
              id="review-comment"
              className="w-full h-32 rounded-lg border bg-background p-3 text-sm resize-none"
              placeholder="What could be improved? What works well?"
              value={commentText}
              onChange={(e) => setCommentText(e.target.value)}
              maxLength={5000}
            />
          </div>

          <Button onClick={submitComment} disabled={submitting || !commentText.trim()} className="w-full">
            {submitting ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Send className="h-4 w-4 mr-2" />}
            Submit Feedback
          </Button>
        </div>

        {/* Footer */}
        <div className="text-center text-xs text-muted-foreground py-4">
          Powered by <span className="font-medium">HireStack AI</span>
        </div>
      </div>
    </div>
  );
}
