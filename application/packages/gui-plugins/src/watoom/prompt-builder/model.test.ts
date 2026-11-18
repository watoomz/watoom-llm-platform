import { describe, expect, test } from "bun:test"
import {
  composePrompt,
  missingFields,
  readPromptSkills,
  loadPromptSkills,
  suggestPipeline,
  suppliedAnswers,
  defaultAnswers,
} from "./model"

const creator = {
  version: 1,
  kind: "creator",
  instructions: ["Preserve the user's dimensions. Reconcile existing jobs before retrying."],
}

const pipeline = {
  version: 1,
  kind: "pipeline",
  id: "blender-builder",
  title: "Blender asset",
  category: "3D",
  availability: "available",
  keywords: ["bench", "blender"],
  fields: [
    { id: "dimensions", label: "Dimensions", help: "Width × depth × height, with units", required: true },
    { id: "target", label: "Engine", help: "Target engine", required: true },
  ],
}

// A prompt-builder block as a skill author writes it, deliberately invalid ones included.
const skill = <Block extends { version: number; kind: string }>(name: string, value: Block, guidance = "") => ({
  name,
  content: guidance + "\n```prompt-builder\n" + JSON.stringify(value) + "\n```\n",
})

const catalog = () =>
  readPromptSkills([
    skill("watoom-prompt-creator", creator),
    skill("watoom-prompt-blender-builder", pipeline, "Keep preview floors out of runtime source."),
  ])

describe("skill-driven prompt builder", () => {
  test("reads maintained skills and keeps contract metadata out of the copied prompt", () => {
    const data = catalog()

    const result = composePrompt(
      data.creator,
      data.recipes[0],
      "Make a bench",
      { dimensions: "1.6 × 0.5 × 0.85 m", target: "Godot and Unreal" },
      "",
    )

    expect(result).toContain("1.6 × 0.5 × 0.85 m")
    expect(result).toContain("Keep preview floors out of runtime source.")
    expect(result).not.toContain('"keywords"')
    expect(result).not.toContain("```prompt-builder")
  })
  test("safe defaults remain editable and explicit supplied settings take priority", () => {
    const recipe = {
      ...catalog().recipes[0],
      fields: catalog().recipes[0].fields.map((field) => ({
        ...field,
        default: field.id === "target" ? "Godot 4.7.2" : "Propose sensible dimensions",
      })),
    }

    expect(defaultAnswers(recipe, "bench").target).toBe("Godot 4.7.2")
    expect(defaultAnswers(recipe, "bench for Unreal 5.8.3").target).toBe("Unreal 5.8.3")
    expect(defaultAnswers(recipe, "bench").dimensions).toBe("Propose sensible dimensions")
  })
  test("asks for essential dimensions without inventing them", () => {
    expect(missingFields(catalog().recipes[0], { target: "Godot" }).map((x) => x.id)).toEqual(["dimensions"])
    expect(() => composePrompt(catalog().creator, catalog().recipes[0], "bench", {}, "")).toThrow("PROMPT_INCOMPLETE")
  })
  test("recognises supplied units, budgets and engine versions", () => {
    expect(suppliedAnswers("Bench 1.6 x 0.5 x 0.85 m under 2,000 triangles for Godot 4.7.2 and Unreal 5.8.3")).toEqual({
      dimensions: "1.6 x 0.5 x 0.85 m",
      budget: "under 2,000 triangles",
      target: "Godot 4.7.2 and Unreal 5.8.3",
    })
    expect(suppliedAnswers("Bench 1.6 m wide").dimensions).toBeUndefined()
  })
  test("suggests a pipeline from the request with word boundaries", () => {
    expect(suggestPipeline("make a park bench", catalog().recipes)).toBe("blender-builder")
    expect(suggestPipeline("benchmark code", catalog().recipes)).toBe("")
    expect(suggestPipeline("unrelated request", catalog().recipes)).toBe("")
  })
  test("fails visibly for missing, malformed, duplicate or unsupported skills", () => {
    expect(() => readPromptSkills([])).toThrow()
    expect(() => readPromptSkills([skill("watoom-prompt-creator", { ...creator, version: 2 })])).toThrow()
    expect(() =>
      readPromptSkills([
        skill("watoom-prompt-creator", creator),
        skill("watoom-prompt-blender-builder", pipeline),
        skill("watoom-prompt-duplicate", pipeline),
      ]),
    ).toThrow()
    expect(() => readPromptSkills([{ name: "watoom-prompt-broken", content: "no contract" }])).toThrow()
  })
  test("confines supplied project paths and preserves literal task content", () => {
    const data = catalog()
    const args = { dimensions: "1 × 2 × 3 cm", target: "Godot" }

    for (const project of [
      "/etc",
      "/data/ai/projects/pipelines/../secrets",
      "/workspace/../etc",
      "/workspace-other/images",
      "/data/ai/projects/images/../secrets",
    ])
      expect(() => composePrompt(data.creator, data.recipes[0], "bench", args, project)).toThrow("PROMPT_PROJECT")
    expect(
      composePrompt(data.creator, data.recipes[0], "A <wooden> bench", args, "/data/ai/projects/pipelines/bench-v1"),
    ).toContain("A <wooden> bench")
    expect(composePrompt(data.creator, data.recipes[0], "A forest image", args, "/workspace/images")).toContain(
      "Project: /workspace/images",
    )
  })
})

test("an empty startup catalog is retried before reporting missing prompt skills", async () => {
  let calls = 0
  await expect(
    loadPromptSkills(async () => {
      calls++

      return calls === 1 ? [] : [{ name: "ordinary-skill", content: "not a prompt skill" }]
    }),
  ).rejects.toThrow("PROMPT_SKILL_CATALOG")
  expect(calls).toBe(2)
})

test("accepts named canonical project categories including image projects", () => {
  const data = catalog()

  for (const project of [
    "/data/ai/projects/images",
    "/data/ai/projects/images/forest-v1",
    "/data/ai/projects/textures",
  ])
    expect(
      composePrompt(
        data.creator,
        data.recipes[0],
        "A forest image",
        { dimensions: "1024 square", target: "image" },
        project,
      ),
    ).toContain("Project: " + project)
})

describe("image prose and tag layout", () => {
  const image = () =>
    readPromptSkills([
      skill("watoom-prompt-creator", creator),
      skill("watoom-prompt-image", {
        ...pipeline,
        id: "image",
        fields: ["description", "scores", "tags", "negative-scores", "exclusions"].map((id) => ({
          id,
          label: id,
          help: "",
          required: false,
        })),
        format: {
          kind: "prose-tags",
          descriptionField: "description",
          positiveFields: ["scores", "tags"],
          negativeFields: ["negative-scores", "exclusions"],
          positiveLabel: "Positive prompt",
          negativeLabel: "Negative prompt",
          settingsLabel: "Execution settings",
        },
      }),
    ])

  test("combines descriptive prose and comma-separated positive tags without mixing negatives", () => {
    const data = image()

    const result = composePrompt(
      data.creator,
      data.recipes[0],
      "Create a park illustration",
      {
        description: "A wooden bench in a sunny park.",
        scores: "score_9, score_8_up",
        tags: "scenery, outdoors, scenery",
        "negative-scores": "score_6, score_5",
        exclusions: "watermark, blurry",
      },
      "/data/ai/projects/images",
    )

    expect(result.split("Negative prompt:")[0]).toBe(
      "Positive prompt:\nA wooden bench in a sunny park. score_9, score_8_up, scenery, outdoors\n\n",
    )
    expect(result).toContain("Negative prompt:\nscore_6, score_5, watermark, blurry")
    expect(result).toContain("Execution settings:")
    expect(result).toContain("Project: /data/ai/projects/images")
    expect(result).not.toContain("- scores:")
  })
  test("uses the main description when the separate box is blank and omits empty negatives", () => {
    const data = image()
    const result = composePrompt(data.creator, data.recipes[0], "A quiet forest.", { tags: "scenery, , " }, "")
    expect(result.startsWith("Positive prompt:\nA quiet forest. scenery\n")).toBe(true)
    expect(result).not.toContain("Negative prompt:")
  })
  test("rejects format references to missing form fields", () => {
    expect(() =>
      readPromptSkills([
        skill("watoom-prompt-creator", creator),
        skill("watoom-prompt-image", {
          ...pipeline,
          format: {
            kind: "prose-tags",
            descriptionField: "missing",
            positiveFields: [],
            negativeFields: [],
            positiveLabel: "Positive",
            negativeLabel: "Negative",
            settingsLabel: "Settings",
          },
        }),
      ]),
    ).toThrow("PROMPT_SKILL_FORMAT")
  })
})
