/**
 * api.js — ZaminTahlil Unified API Client
 * Standardized HTTP client with error normalization, abort controller support,
 * and typed service calls matching the backend FastAPI endpoints.
 */

(function () {
  "use strict";

  class ApiError extends Error {
    constructor(status, message, detail = null) {
      super(message);
      this.name = "ApiError";
      this.status = status;
      this.detail = detail;
    }
  }

  async function normalizeError(response) {
    let detail = null;
    let message = "Noma'lum xatolik yuz berdi";
    try {
      const data = await response.json();
      detail = data.detail || data;
      if (typeof detail === "string") {
        message = detail;
      } else if (Array.isArray(detail) && detail[0]?.msg) {
        message = detail.map((d) => d.msg).join("; ");
      } else if (data.message) {
        message = data.message;
      }
    } catch {
      message = response.statusText || `Xatolik (${response.status})`;
    }

    if (response.status === 400 && !detail) {
      message = "So'rov parametri noto'g'ri (400).";
    } else if (response.status === 404) {
      message = message || "Resurs topilmadi (404).";
    } else if (response.status === 409) {
      message = message || "Bu ma'lumot allaqachon mavjud (409).";
    } else if (response.status === 422) {
      message = message || "Ma'lumotlar formati yaroqsiz (422).";
    } else if (response.status >= 500) {
      message = "Serverda ichki xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring.";
    }

    return new ApiError(response.status, message, detail);
  }

  const api = {
    async request(url, options = {}) {
      const headers = {
        "Accept": "application/json",
        ...options.headers,
      };

      const token = localStorage.getItem("zamintahlil_token");
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const config = {
        headers,
        ...options,
      };

      if (config.body && typeof config.body === "object" && !(config.body instanceof FormData)) {
        config.headers["Content-Type"] = "application/json";
        config.body = JSON.stringify(config.body);
      }


      try {
        const response = await fetch(url, config);
        if (!response.ok) {
          throw await normalizeError(response);
        }
        if (response.status === 204) {
          return null;
        }
        return await response.json();
      } catch (err) {
        if (err.name === "AbortError") {
          throw err;
        }
        if (err instanceof ApiError) {
          throw err;
        }
        throw new ApiError(0, "Serverga ulanib bo'lmadi. Aloqani tekshiring.", err);
      }
    },

    get(url, params = null, signal = null) {
      let finalUrl = url;
      if (params) {
        const search = new URLSearchParams();
        for (const [key, val] of Object.entries(params)) {
          if (val !== null && val !== undefined && val !== "") {
            search.append(key, val);
          }
        }
        const qs = search.toString();
        if (qs) finalUrl += (url.includes("?") ? "&" : "?") + qs;
      }
      return this.request(finalUrl, { method: "GET", signal });
    },

    post(url, body = null, signal = null) {
      return this.request(url, { method: "POST", body, signal });
    },

    patch(url, body = null, signal = null) {
      return this.request(url, { method: "PATCH", body, signal });
    },

    delete(url, body = null, signal = null) {
      return this.request(url, { method: "DELETE", body, signal });
    },

    // Health
    getHealth(signal) {
      return this.get("/api/health", null, signal);
    },

    // Auth
    register(userData, signal) {
      return this.post("/api/auth/register", userData, signal);
    },

    login(credentials, signal) {
      return this.post("/api/auth/login", credentials, signal);
    },

    getMe(signal) {
      return this.get("/api/auth/me", null, signal);
    },

    // Fields
    getFields(signal) {
      return this.get("/api/fields", null, signal);
    },

    getField(fieldId, signal) {
      return this.get(`/api/fields/${fieldId}`, null, signal);
    },

    createField(fieldData, signal) {
      return this.post("/api/fields", fieldData, signal);
    },

    purgeFields(confirmation = "roziman", signal) {
      return this.post("/api/database/purge-fields", { confirmation }, signal);
    },

    // Satellite & Analysis
    analyzeField(fieldId, mode = "latest", signal) {
      return this.post(`/api/fields/${fieldId}/analyze`, { mode }, signal);
    },

    getAcquisitions(fieldId, signal) {
      return this.get(`/api/fields/${fieldId}/acquisitions`, null, signal);
    },

    getArtifacts(fieldIdOrAcq, acquisitionId = null, signal = null) {
      let fieldId = fieldIdOrAcq;
      let acqId = acquisitionId;
      if (typeof fieldIdOrAcq === "object" && fieldIdOrAcq !== null) {
        fieldId = fieldIdOrAcq.field_id;
        acqId = fieldIdOrAcq.id;
      } else if (acqId === null) {
        acqId = fieldIdOrAcq;
        fieldId = window.state?.selectedField?.id;
      }
      return this.get(`/api/fields/${fieldId}/acquisitions/${acqId}/artifacts`, null, signal);
    },

    getAnnualMetrics(fieldId, year = null, signal = null) {
      const selectedYear = year || new Date().getFullYear();
      return this.get(`/api/fields/${fieldId}/annual-metrics`, { year: selectedYear }, signal);
    },

    getHistoricalMetrics(fieldId, fromDate = null, toDate = null, signal = null) {
      const from_date = fromDate || `${new Date().getFullYear()}-01-01`;
      return this.post(`/api/fields/${fieldId}/historical-metrics`, { from_date }, signal);
    },

    getRecommendation(fieldId, signal) {
      return this.get(`/api/fields/${fieldId}/recommendation`, null, signal);
    },

    // Yield Prediction
    getYieldModels(signal) {
      return this.get("/api/yield/models", null, signal);
    },

    predictYield(fieldId, data = {}, signal) {
      return this.post(`/api/fields/${fieldId}/predict-yield`, data, signal);
    },

    getLatestYield(fieldId, signal) {
      return this.get(`/api/fields/${fieldId}/yield-latest`, null, signal);
    },

    // AI Agronom Chat
    getChatHistory(fieldId, signal) {
      return this.get(`/api/fields/${fieldId}/chat/history`, null, signal);
    },

    getChatSummary(fieldId, signal) {
      return this.get(`/api/fields/${fieldId}/chat/summary`, null, signal);
    },

    sendChatMessage(fieldId, payload, signal) {
      let body = payload;
      if (payload && payload.message && !payload.messages) {
        body = {
          messages: [{ role: "user", content: payload.message }],
          rag_mode: payload.rag_mode || "advanced",
          language: payload.language || (window.i18n ? window.i18n.getLanguage() : "uz-latn"),
          selected_book_ids: payload.selected_book_ids || null,
        };
      }
      return this.post(`/api/fields/${fieldId}/chat`, body, signal);
    },

    // Knowledge Base & RAG Books
    getRagBooks(signal) {
      return this.get("/api/rag/books", null, signal);
    },

    toggleRagBook(bookId, isActive, signal) {
      return this.post(`/api/rag/books/${bookId}/toggle`, { is_active: isActive }, signal);
    },
  };

  window.api = api;
  window.ApiError = ApiError;
})();
