import { getFieldsFromUrl } from "../lti/lti";

const API_BASE = import.meta.env.PROD ? "https://apiaws.glossalearn.com/api" : "http://127.0.0.1:8080/api";
const TEXT_API_BASE = import.meta.env.PROD ? "https://apiaws.glossalearn.com" : "http://127.0.0.1:8080";
const LAUNCH_API_TOFILL = "LAUNCH_ID_TOFILL";

const fetchRetry = async (url, obj) => {
    let lastErr

    for (let i = 0; i < 10; i++) {
        try {
            const res = await fetch(url, obj)

            if (res.status !== 418) {
                return res
            }

            lastErr = new Error(`418 retry ${i + 1}`)
        } catch (err) {
            lastErr = err
        }

        await new Promise(r =>
            setTimeout(r, 50)
        )
    }

    throw lastErr
}

async function glossaFetch(url, obj) {
    const { launch_id, deployment_id, deployment_url } = getFieldsFromUrl();
    const toAdd = '?' + new URLSearchParams({
        deployment_id, deployment_url
    }).toString();
    const filledUrl = url.replace(LAUNCH_API_TOFILL, launch_id) + (url.includes("works") || url.includes("authors") || url.includes("sentence") ? "" : toAdd);
    const response = await fetchRetry(filledUrl, obj);
    if (!response.ok) {
        throw new Error("Failed to fetch assignments");
    }
    const res = await response.json();
    console.log(res);
    return res;
}

export const getAssignments = () => glossaFetch(`${API_BASE}/assignments/${LAUNCH_API_TOFILL}`);

export const getSubmissions = () => glossaFetch(`${API_BASE}/submissions/${LAUNCH_API_TOFILL}`);

const preparePost = (payload) => {
    return {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ ...payload }),

    };
}

export const createAssignment = (payload) => glossaFetch(`${API_BASE}/assignment/${LAUNCH_API_TOFILL}`, preparePost(payload));

export const createSubmission = (payload) => glossaFetch(`${API_BASE}/submission/${LAUNCH_API_TOFILL}`, preparePost(payload));

export const submitSubmission = (payload) => glossaFetch(`${API_BASE}/submission/${LAUNCH_API_TOFILL}/submit`, preparePost(payload));
export const gradeSubmission = (payload) => glossaFetch(`${API_BASE}/submission/${LAUNCH_API_TOFILL}/grade`, preparePost(payload));


export const getWorks = (author) => glossaFetch(`${TEXT_API_BASE}/api/works?author=${author}`);

export const getAuthors = () => glossaFetch(`${TEXT_API_BASE}/api/authors`);

export const getWorkSentences = async (workId) => glossaFetch(`${TEXT_API_BASE}/api/sentences?work_id=${workId}`);
export const getSentence = async (id) => glossaFetch(`${TEXT_API_BASE}/api/sentence?id=${id}`);

export async function sendAudioToServer(blob, language) {
    const copy = await fetch(blob).then((r) => r.blob());
    const formData = new FormData();
    formData.append("file", new File([copy], "recording.webm", { type: copy.type }));
    formData.append("language", language);

    try {
      const response = await fetch(`${TEXT_API_BASE}/transcribe`, {
        method: "POST",
        body: formData
      });

      const data = await response.json();
      console.log(data);
      return data.text;
    } catch (err) {
      console.log("Failed to send audio:", err);
      return null;
    }
  }

export async function uploadAudio(blob) {
    const copy = await fetch(blob).then((r) => r.blob());
    const formData = new FormData();
    formData.append("file", new File([copy], "recording.webm", { type: copy.type }));

    try {
      const response = await fetch(`${TEXT_API_BASE}/upload`, {
        method: "POST",
        body: formData
      });

      const data = await response.json();
      return data?.uuid;
    } catch (err) {
      console.log("Failed to send audio:", err);
      return null;
    }
  }

  export async function getUserUpload(uuid) {
    const response = await fetch(`${TEXT_API_BASE}/upload?uuid=${uuid}`);
    console.log(response);
    const blob = await response.blob();
    return URL.createObjectURL(blob);
  }