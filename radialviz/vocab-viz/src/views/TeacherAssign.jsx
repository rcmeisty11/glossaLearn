import { useEffect, useState } from "react";

import {
  createAssignment,
  getAssignments,
  getAuthors,
  getWorks,
  getWorkSentences
} from "../api/api";

export default function TeacherAssign() {
  const [assignments, setAssignments] =
    useState([]);

  const [assignmentType, setAssignmentType] =
    useState("translation");

  const [authors, setAuthors] = useState([]);
  const [selectedAuthor, setSelectedAuthor] =
    useState("");

  const [works, setWorks] = useState([]);
  const [selectedWork, setSelectedWork] =
    useState("");

  const [sentences, setSentences] =
    useState([]);

  const [selectedSentence, setSelectedSentence] =
    useState("");

  const [created, setCreated] =
    useState(false);

  useEffect(() => {
    loadAssignments();
    loadAuthors();
  }, []);

  useEffect(() => {
    if (!selectedAuthor) return;

    loadWorks(selectedAuthor);
  }, [selectedAuthor]);

  
  // once work is selected, load sentences
  useEffect(() => {
    if (!selectedWork) return;

    loadSentences(selectedWork);
  }, [selectedWork]);

  async function loadAssignments() {
    setAssignments(await getAssignments());
  }

  async function loadAuthors() {
    setAuthors(await getAuthors().authors || []);
  }

  async function loadWorks(author) {
    setWorks(await getWorks(author).works || []);
  }

  async function loadSentences(workId) {
    setSentences(await getWorkSentences(workId).sentences || []);
  }

  function handleAuthorChange(value) {
    setSelectedAuthor(value);

    setSelectedWork("");
    setSelectedSentence("");
    setWorks([]);
    setSentences([]);
  }

  function handleWorkChange(value) {
    setSelectedWork(value);
    // clear others, TODO: we should validate this on the backend (though we cannot enforce it by schema as we have 2 different dbs)
    setSelectedSentence("");
    setSentences([]);
  }

  async function handleCreateAssignment() {
    // TODO: assignmentIds should be set by db automatically
    const assignmentId =
      crypto.randomUUID();

    await createAssignment({

      assignment_id: assignmentId,
      assignment_type: assignmentType,
      author: selectedAuthor,
      work: selectedWork,
      sentence_id: selectedSentence
    });

    setCreated(true);

    await loadAssignments();
  }

  return (
    <div>
      <div>
        <div>
          <h2>Create Assignment</h2>
        </div>

        <div>
          <div>
            <div>
              <label>
                Assignment Type
              </label>

              <select
                value={assignmentType}
                onChange={e =>
                  setAssignmentType(
                    e.target.value
                  )
                }

                className="glossalearn-input"
              >
                <option value="translation">
                  Translation
                </option>

                <option value="production">
                  Production
                </option>

                <option value="perception">
                  Perception
                </option>
              </select>
            </div>

            <div>
              <label>Author</label>

              <select
                value={selectedAuthor}
                onChange={e =>
                  handleAuthorChange(
                    e.target.value
                  )
                }

                className="glossalearn-input"
              >
                <option value="">
                  Select Author
                </option>

                {authors.map(author => (
                  <option
                    value={author.author}
                  >
                    {author.author}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label>Work</label>

              <select
                value={selectedWork}
                onChange={e =>
                  handleWorkChange(
                    e.target.value
                  )
                }

                className="glossalearn-input"
              >
                <option value="">
                  Select Work
                </option>
                {selectedAuthor}
                {works.filter(work => {
                  return work.author === selectedAuthor
                }).map(work => (
                  <option
                    key={work.title}
                    value={work.title}
                  >
                    {work.title}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div style={{ marginTop: "10px" }}>
            <label>Sentence</label>

            <select
              value={selectedSentence}
              onChange={e =>
                setSelectedSentence(
                  e.target.value
                )
              }

              className="glossalearn-input"
            >
              <option value="">
                Select Sentence
              </option>

              {sentences.map(sentence => (
                <option
                  key={sentence.id}
                  value={sentence.id}
                >
                  {sentence.text}
                </option>
              ))}
            </select>
          </div>

          <button
            className="glossalearn-button"
            onClick={handleCreateAssignment}
          >
            Create Assignment
          </button>

          {created && (
            <p>
              Assignment created.
            </p>
          )}
        </div>
      </div>

      <div >
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



                  <div>Author: {assignment.author} Work: {assignment.work} Sentence: {assignment.sentence_id}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}