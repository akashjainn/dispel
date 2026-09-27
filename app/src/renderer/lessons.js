// What the wizard teaches in Learn mode. Each page must fit in the speech
// bubble (about 45 words). Keep the copy honest: no page may promise that the
// wizard, or any detector, can prove a voice is real or fake.

const LESSONS = {
  deepfake: {
    title: 'What’s a deepfake?',
    pages: [
      'A deepfake is audio or video made by AI to look or sound like a real person. A voice deepfake can say words that person never said.',
      'Copying a voice is cheap now. Some tools need less than a minute of someone talking, like a clip from a video they posted, to sound like them.',
      'A fake can be a recording made from typed text, or a live call where a scammer’s voice is turned into someone else’s as they talk.',
      'Fakes often slip on small things: breathing, pauses, emotion that doesn’t fit the moment, names said oddly. But good ones can fool anyone, sometimes even me.',
    ],
  },
  scams: {
    title: 'Common deepfake scams',
    pages: [
      'The family emergency. A call that sounds like your grandchild, child or friend: they’re hurt, arrested or stranded, need money right now, and beg you not to tell anyone.',
      'The fake kidnapping. A crying voice that sounds like someone you love, then a stranger demanding ransom. The goal is panic, so you pay before you check.',
      'The boss on the line. A call or video meeting where a manager asks for an urgent transfer. In 2024 a worker in Hong Kong sent about $25 million after a video call full of deepfaked colleagues.',
      'Fake officials and banks. A “fraud department”, police officer or government agent who sounds official and needs you to move money or read out a code.',
      'Fake public figures. Cloned voices of politicians and celebrities pushing investments, giveaways or false news. In 2024, New Hampshire voters got robocalls with an AI copy of President Biden’s voice.',
      'The pattern to watch for: urgency, secrecy, and a payment that’s hard to undo, like a wire transfer, gift cards or crypto. When you notice these, stop and check.',
    ],
  },
  protect: {
    title: 'Protect yourself and your family',
    pages: [
      'Pick a family safe word: a word or question only your family knows. If a caller can’t answer it, hang up. Set one up today, especially with grandparents and kids.',
      'Hang up and call back on a number you already have saved, not the one that called you. Caller ID can be faked too.',
      'Slow down. A real emergency can wait five minutes while you check. Anyone who pressures you to stay on the line or keep it secret is a red flag.',
      'Ask something only the real person would know that isn’t online: a family joke, or what you ate the last time you were together.',
      'Be careful with your voice online. Public videos can be used to copy how you sound. Consider making accounts private.',
      'Talk about this with the people you love, especially older relatives, who are often targeted. Two minutes now can save a lot of pain later.',
      'If it happens: stop sending money, call your bank right away, and report it. In the US, use reportfraud.ftc.gov and ic3.gov. These scams fool smart people; there’s no shame in it.',
      'I can help spot voices that are likely synthetic, but I can’t prove anything. Your safe word and a call back are stronger than any detector, including me.',
    ],
  },
};

const LESSON_TOPICS = Object.keys(LESSONS);
