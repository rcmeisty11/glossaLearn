import { useEffect, useState, useRef } from "react";
import { ReactMediaRecorder } from "react-media-recorder";

import {
  getAssignments,
  createSubmission,
  submitSubmission,
  getSubmissions,
  getSentence,
  uploadAudio
} from "../api/api";


export default function StudentAnswer() {
  const [assignments, setAssignments] =
    useState([]);
  const [submissions, setSubmissions] =
    useState([]);



  const [selectedAssignment, setSelectedAssignment] =
    useState(null);

  const [answer, setAnswer] = useState("");

  const [submitted, setSubmitted] =
    useState(false);

  const [sentenceText, setSentenceText] = useState("");

  let mediaBlobUrl = useRef('');
  const [recording, setRecording] = useState(false);

  useEffect(() => {
    loadAssignments();
    loadSubmissions();
  }, []);

  useEffect(() => {
    loadSentenceText();
  }, [selectedAssignment]);

  async function loadSentenceText() {
    const sentence = await getSentence(selectedAssignment?.sentence_id || "");
    console.log(selectedAssignment, sentence);
    setSentenceText((sentence)?.sentence?.text || "");
  }

  async function loadAssignments() {
    setAssignments(await getAssignments());
  }

  async function loadSubmissions() {
    setSubmissions(await getSubmissions());
  }

  async function openAssignment(assignment) {
    setSelectedAssignment(assignment);
    setSubmitted(false);
    const existingAssignmentAnswer = submissions.find((sub) => sub.assignment_id == assignment.assignment_id)?.assignment_artifact || '';
    setAnswer(existingAssignmentAnswer);

    await createSubmission({

      assignment_id:
        assignment.assignment_id,

      assignment_artifact: existingAssignmentAnswer
    });
  }

  async function handleSubmit() {
    if (!selectedAssignment) return;

    let userAnswer = answer;
    if (selectedAssignment.assignment_type === "production") {
      console.log(mediaBlobUrl);
      const uuid = await uploadAudio(mediaBlobUrl);
      userAnswer = uuid;
    }

    await submitSubmission({
      assignment_id:
      selectedAssignment.assignment_id,
      assignment_artifact: userAnswer
    });

    setSubmitted(true);
  }

  return (
    <div>
      <div>
        <div>
          <h2>Assignments</h2>
        </div>

        <div>
          {assignments.map(assignment => (
            <div

              key={assignment.assignment_id}
            >
              <div>
                <div>
                  {
                    assignment.assignment_type
                  }
                </div>

                <div>
                  {
                    assignment.assignment_id
                  }
                </div>
              </div>

              <button
                className='glossalearn-button'
                onClick={() =>
                  openAssignment(assignment)
                }
              >
                Open
              </button>
            </div>
          ))}
        </div>
      </div>

      {selectedAssignment && (
        <div>
          <div>
            <h2>
              {
                selectedAssignment.assignment_type
              }
            </h2>
          </div>
          <div>
            Author: {selectedAssignment.author}
          </div>
          <div>
            Work: {selectedAssignment.work}
          </div>
          <div>
            Sentence: {sentenceText}
          </div>
          <div>
            <label>Response</label>

            {selectedAssignment.assignment_type !== "production" && <textarea
              value={answer}
              onChange={e =>
                setAnswer(e.target.value)
              }
              className="glossalearn-input"
            />}

            {selectedAssignment.assignment_type === "production" && <ReactMediaRecorder
              render={({ status, startRecording, stopRecording, mediaBlobUrl: blobUrl }) => {
                mediaBlobUrl = blobUrl;
                return (
                  <div>
                    <button style={{
                      padding: "2px 7px", borderRadius: 3, fontSize: 11, fontWeight: 600,
                      letterSpacing: .3, cursor: "pointer", fontFamily: "'EB Garamond',Georgia,serif",
                      background: "transparent",
                      color: 'white',
                      border: `1px solid #3d372e`,
                      opacity: 0.6,
                    }}
                      onClick={(e) => {
                        const innerRec = recording;
                        setRecording(!innerRec);
                        return innerRec ? stopRecording(e) : startRecording(e);
                      }}>{recording ? 'Stop' : 'Start'} Recording</button>
                    <div>
                      {blobUrl && <video src={blobUrl} controls autoPlay loop />}</div>
                  </div>
                )
              }}
            />}

            <button
              className="glossalearn-button"
              onClick={handleSubmit}
            >
              Submit Assignment
            </button>

            {submitted && (
              <p>
                Assignment submitted.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}