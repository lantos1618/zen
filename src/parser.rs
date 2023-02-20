use serde::{Serialize};
use crate::ast::{Expr, Literal, Identifier, Ellipse, Assignment, Key, Body};
use crate::tokenizer::{Token, Tokenizer, self};


#[derive(Debug, PartialEq, Serialize)]
pub enum ParseError {
    UnexpectedToken(Token),
    UnexpectedEOF,
}

pub struct Parser<'a> {
    tokens: std::iter::Peekable<Tokenizer<'a>>,
}

impl<'a> Parser<'a> {
    pub fn new(input: &'a str) -> Parser<'a> {
        Parser {
            tokens: Tokenizer::new(input).peekable(),
        }
    }

    fn next_token(&mut self) -> Result<Token, ParseError> {
        self.tokens.next().ok_or(ParseError::UnexpectedEOF)
    }

    fn parse_string_literal(&mut self) -> Result<Expr, ParseError> {
        if let Token::StringLiteral(value) = self.next_token()? {
            Ok(Expr::Literal(Literal::StringLiteral(value)))
        } else {
            Err(ParseError::UnexpectedToken(self.tokens.next().unwrap()))
        }
    }

    fn parse_number_literal(&mut self) -> Result<Expr, ParseError> {
        if let Token::IntLiteral(value) = self.next_token()? {
            Ok(Expr::Literal(Literal::IntLiteral(value)))
        } else if let Token::FloatLiteral(value) = self.tokens.next().unwrap() {
            Ok(Expr::Literal(Literal::FloatLiteral(value)))
        } else {
            Err(ParseError::UnexpectedToken(self.tokens.next().unwrap()))
        }
    }

    fn parse_identifier(&mut self) -> Result<Expr, ParseError> {
        // 
        // identifier(...) = L Token::ParenOpen         R
        // identifier{...} = L Token::CurlyBraceOpen    R
        // identifier:...  = L Token::Colon             R


        // need a way to do L ,Token, R 

        if let Token::Identifier(name) = self.next_token()? {
            match self.tokens.peek() {
                Some(Token::ParenOpen) => todo!(),
                Some(Token::CurlyBraceOpen) => todo!(),
                Some(Token::Colon) => todo!(),
                _ => Ok(Expr::Identifier(Identifier(name))),
            }
        } else {
            Err(ParseError::UnexpectedToken(self.tokens.next().unwrap()))
        }

    }

    fn parse_ellipse(&mut self) -> Result<Expr, ParseError> {
        // ...identifier
        if let Token::Identifier(name) = self.next_token()? {
            Ok(Expr::Ellipse(Ellipse(Identifier(name))))
        } else {
            Err(ParseError::UnexpectedToken(self.tokens.next().unwrap()))
        }
    }
    fn parse_dot(&mut self) -> Result<Expr, ParseError> {
        // L , Token::Dot, R
        if let Token::Dot = self.next_token()? {
            Ok(Expr::Identifier(Identifier(".".to_string())))
        } else {
            Err(ParseError::UnexpectedToken(self.tokens.next().unwrap()))
        }
    }

    fn parse_body(&mut self) -> Result<Expr, ParseError> {
        // { ... }
        let mut fields = Vec::new();
        while let Some(token) = self.tokens.peek() {
            match token {
                Token::Newline(_) | Token::WhiteSpace(_) => {
                    self.tokens.next();
                },
                Token::CurlyBraceOpen => {
                    fields.push(self.parse_body()?);
                }
                Token::CurlyBraceClose => {
                    self.tokens.next();
                    break;
                }
                _ => {
                    fields.push(self.parse_primary()?);
                }
            }
        }
        Ok(Expr::Body(Body { fields }))
    }

    fn parse_assignment(&mut self) -> Result<Expr, ParseError> {
        // identifier: ...  = L Token::Colon, R
        // {...}: ...       = L Token::Colon, R

        let mut key = Vec::new();
        let mut value = None;
        while let Some(token) = self.tokens.peek() {
            match token {
                Token::Identifier(name) => {
                    key.push(Identifier(name.to_string()));
                    self.tokens.next();
                }
                Token::Colon => {
                    self.tokens.next();
                    value = Some(self.parse_primary()?);
                    break;
                }
                _ => {
                    return Err(ParseError::UnexpectedToken(self.tokens.next().unwrap()));
                }
            }
        }
        if key.len() == 1 {
            Ok(Expr::Assignment(Assignment {
                key: Key::Key(key.pop().unwrap()),
                value: Box::new(value.unwrap()),
            }))
        } else {
            Ok(Expr::Assignment(Assignment {
                key: Key::DestructureKeys(key),
                value: Box::new(value.unwrap()),
            }))
        }
    }

    fn parse_primary(&mut self) -> Result<Expr, ParseError> {
        // what can we expect to see on at the root of the file or body
        if let Some(token) = self.tokens.peek() {
            match token {
                // Token::StringLiteral(_) => self.parse_string_literal(),
                // Token::IntLiteral(_) | Token::FloatLiteral(_) => self.parse_number_literal(),
                // Token::Ellipse => self.parse_ellipse(),
                Token::CurlyBraceOpen => self.parse_body(),
                Token::Identifier(_) => self.parse_identifier(),
                // Token::Dot => self.parse_dot(),
                _ => Err(ParseError::UnexpectedToken(self.tokens.next().unwrap())),
            }
        } else {
            Err(ParseError::UnexpectedEOF)
        }
    }


    fn parse_expr(&mut self) -> Result<Expr, ParseError> {
        let mut expr = self.parse_primary()?;
        loop {
            if let Some(token) = self.tokens.peek() {
                match token {
                    Token::Newline(_) => {
                        self.tokens.next();
                    }
                    _ => {
                        break;
                    }
                }
            } else {
                break;
            }
        }
        Ok(expr)
    }

    pub fn parse(&mut self) -> Result<Expr, ParseError> {
        self.parse_expr()
    }
}

#[test]
fn test_ast() {

    let name_str = "Name: Type {
        fistName: String,
        lastName: String,
    }";
    let mut parser = Parser::new(name_str);
    let name_ast = match(parser.parse()) {
        Ok(ast) => ast,
        Err(e) => panic!("Error: {:?}", e)
    };

    println!("{:?}", name_ast);

    let name_ast_expected = Expr::Assignment(Assignment{
        key: Key::Key(Identifier("Name".to_string())),
        value: Box::new(Expr::Body(Body {
            fields: vec![
                Expr::Assignment(Assignment{
                    key: Key::Key(Identifier("fistName".to_string())),
                    value: Box::new(Expr::Identifier(Identifier("String".to_string()))),
                }),
                Expr::Assignment(Assignment{
                    key: Key::Key(Identifier("lastName".to_string())),
                    value: Box::new(Expr::Identifier(Identifier("String".to_string()))),
                }),
            ]
        })),
    });

    assert!(name_ast == name_ast_expected);

    // {
    //     x: Int.i32,
    //     y: Int.i32,
    // }: myPerson.otherFunc1() {
    //     io.print(result.x)
    //     io.print(result.y)
    // }
    // let other_func1_str = "{
    //     x: Int.i32,
    //     y: Int.i32,
    // }: myPerson.otherFunc1() {
    //     io.print(result.x)
    //     io.print(result.y)
    // }";
    // let mut parser = Parser::new(other_func1_str);
    // let other_func1_ast1 = match(parser.parse()) {
    //     Ok(ast) => ast,
    //     Err(e) => panic!("Error: {:?}", e)
    // };

    // println!("other_func1_ast1: {:?}", serde_json::to_string_pretty(&other_func1_ast1).unwrap());

    // let other_func1_ast1_expected = Expr::Assignment(Assignment {
    //     key: Key::DestructureKeysAssignment(vec![
    //         Assignment { 
    //             key: Key::Key(Identifier("x".to_string())), 
    //             value: Box::new(Expr::Accessor(Accessor { 
    //                 name:   Identifier("Int".to_string()),
    //                 field:  Box::new(Expr::Identifier(Identifier("i32".to_string())))
    //             }))
    //         },
    //         Assignment { 
    //             key: Key::Key(Identifier("x".to_string())), 
    //             value: Box::new(Expr::Accessor(Accessor { 
    //                 name:   Identifier("Int".to_string()),
    //                 field:  Box::new(Expr::Identifier(Identifier("i32".to_string())))
    //             }))
    //         }
    //     ]),
    //     value: Box::new(Expr::Accessor(Accessor {
    //         name: Identifier("myPerson".to_string()),
    //         field: Box::new(Expr::Call(Call {
    //             name: Identifier("otherFunc1".to_string()),
    //             args: Box::new(Body { fields: vec![] }),
    //             body: Box::new(Body {
    //                 fields: vec![
    //                     Expr::Accessor(Accessor {
    //                         name: Identifier("io".to_string()),
    //                         field: Box::new(Expr::Call(Call {
    //                             name: Identifier("print".to_string()),
    //                             args: Box::new(Body {
    //                                 fields: vec![Expr::Accessor(Accessor {
    //                                     name: Identifier("result".to_string()),
    //                                     field: Box::new(Expr::Identifier(Identifier(
    //                                         "x".to_string(),
    //                                     ))),
    //                                 })],
    //                             }),
    //                             body: Box::new(Body { fields: vec![] }),
    //                         })),
    //                     }),
    //                     Expr::Accessor(Accessor {
    //                         name: Identifier("io".to_string()),
    //                         field: Box::new(Expr::Call(Call {
    //                             name: Identifier("print".to_string()),
    //                             args: Box::new(Body {
    //                                 fields: vec![Expr::Accessor(Accessor {
    //                                     name: Identifier("result".to_string()),
    //                                     field: Box::new(Expr::Identifier(Identifier(
    //                                         "y".to_string(),
    //                                     ))),
    //                                 })],
    //                             }),
    //                             body: Box::new(Body { fields: vec![] }),
    //                         })),
    //                     }),
    //                 ],
    //             }),
    //         })),
    //     })),
    // });
    // print!("{}", serde_json::to_string_pretty(&other_func1_ast1_expected).unwrap());



    // let other_func1_str = "{ x, y }: myPerson.otherFunc1() {
    //     io.print(result.x)
    //     io.print(result.y)
    // }";
    // let other_func1_ast2_expected = Expr::Assignment(Assignment {
    //     key: Key::DestructureKeys(vec![
    //         Identifier("x".to_string()),
    //         Identifier("y".to_string()),
    //     ]),
    //     value: Box::new(Expr::Accessor(Accessor {
    //         name: Identifier("myPerson".to_string()),
    //         field: Box::new(Expr::Call(Call {
    //             name: Identifier("otherFunc1".to_string()),
    //             args: Box::new(Body { fields: vec![] }),
    //             body: Box::new(Body {
    //                 fields: vec![
    //                     Expr::Accessor(Accessor {
    //                         name: Identifier("io".to_string()),
    //                         field: Box::new(Expr::Call(Call {
    //                             name: Identifier("print".to_string()),
    //                             args: Box::new(Body {
    //                                 fields: vec![Expr::Accessor(Accessor {
    //                                     name: Identifier("result".to_string()),
    //                                     field: Box::new(Expr::Identifier(Identifier(
    //                                         "x".to_string(),
    //                                     ))),
    //                                 })],
    //                             }),
    //                             body: Box::new(Body { fields: vec![] }),
    //                         })),
    //                     }),
    //                     Expr::Accessor(Accessor {
    //                         name: Identifier("io".to_string()),
    //                         field: Box::new(Expr::Call(Call {
    //                             name: Identifier("print".to_string()),
    //                             args: Box::new(Body {
    //                                 fields: vec![Expr::Accessor(Accessor {
    //                                     name: Identifier("result".to_string()),
    //                                     field: Box::new(Expr::Identifier(Identifier(
    //                                         "y".to_string(),
    //                                     ))),
    //                                 })],
    //                             }),
    //                             body: Box::new(Body { fields: vec![] }),
    //                         })),
    //                     }),
    //                 ],
    //             }),
    //         })),
    //     })),
    // });
    // print!("{}", serde_json::to_string_pretty(&other_func1_ast2_expected).unwrap());

    // let other_func2_str = "otherFunc2() {
    //     other1: Person,
    //     other2: String
    // }";
    // let other_func2_ast_expected = Expr::Call(
    //     (Call {
    //         name: Identifier("otherFunc2".to_string()),
    //         args: Box::new(Body { fields: vec![] }),
    //         body: Box::new(Body {
    //             fields: vec![
    //                 Expr::Assignment(Assignment {
    //                     key: Key::Key(Identifier("other1".to_string())),
    //                     value: Box::new(Expr::Identifier(Identifier("Person".to_string()))),
    //                 }),
    //                 Expr::Assignment(Assignment {
    //                     key: Key::Key(Identifier("other2".to_string())),
    //                     value: Box::new(Expr::Identifier(Identifier("String".to_string()))),
    //                 }),
    //             ],
    //         }),
    //     }),
    // );
    // print!("{}", serde_json::to_string_pretty(&other_func2_ast_expected).unwrap());

}

// #[derive(Debug, PartialEq, Serialize)]
// pub enum Expr {
//     Ident(String),
//     IntLit(i64),
//     FloatLit(f64),
//     StringLit(String),
//     Call(),
//     CallWithBody(Box<Expr>, Vec<Expr>, HashMap<String, Expr>),
//     Object(HashMap<String, Expr>),
// }

// #[derive(Debug, PartialEq, Serialize)]
// pub enum ParseError {
//     UnexpectedToken(Token),
//     UnexpectedEOF,
// }

// pub struct Parser<'a> {
//     tokens: std::iter::Peekable<Tokenizer<'a>>,
// }

// impl<'a> Parser<'a> {
//     pub fn new(input: &'a str) -> Parser<'a> {
//         Parser {
//             tokens: Tokenizer::new(input).peekable(),
//         }
//     }

//     fn next_token(&mut self) -> Result<Token, ParseError> {
//         self.tokens.next().ok_or(ParseError::UnexpectedEOF)
//     }

//     fn parse_string_literal(&mut self) -> Result<Expr, ParseError> {
//         if let Token::StringLiteral(value) = self.next_token()? {
//             Ok(Expr::StringLit(value))
//         } else {
//             Err(ParseError::UnexpectedToken(self.tokens.next().unwrap()))
//         }
//     }

//     fn parse_number_literal(&mut self) -> Result<Expr, ParseError> {
//         if let Token::IntLiteral(value) = self.next_token()? {
//             Ok(Expr::IntLit(value))
//         } else if let Token::FloatLiteral(value) = self.tokens.next().unwrap() {
//             Ok(Expr::FloatLit(value))
//         } else {
//             Err(ParseError::UnexpectedToken(self.tokens.next().unwrap()))
//         }
//     }

//     fn parse_ident(&mut self) -> Result<Expr, ParseError> {
//         if let Token::Identifier(name) = self.next_token()? {
//             Ok(Expr::Ident(name))
//         } else {
//             Err(ParseError::UnexpectedToken(self.tokens.next().unwrap()))
//         }
//     }

//     fn parse_primary(&mut self) -> Result<Expr, ParseError> {
//         match self.tokens.peek() {
//             Some(&Token::StringLiteral(_)) => self.parse_string_literal(),
//             Some(&Token::IntLiteral(_)) | Some(&Token::FloatLiteral(_)) => {
//                 self.parse_number_literal()
//             }
//             Some(&Token::Identifier(_)) => self.parse_ident(),
//             Some(&Token::CurlyBraceOpen) => self.parse_object(),
//             Some(&Token::ParenOpen) => {
//                 self.tokens.next();
//                 let expr = self.parse_primary()?;
//                 if let Some(&Token::ParenClose) = self.tokens.peek() {
//                     self.tokens.next();
//                     Ok(expr)
//                 } else {
//                     Err(ParseError::UnexpectedToken(self.tokens.next().unwrap()))
//                 }
//             }
//             _ => Err(ParseError::UnexpectedToken(self.tokens.next().unwrap())),
//         }
//     }

//     fn parse_call(&mut self, func: Expr) -> Result<Expr, ParseError> {
//         let mut args = Vec::new();
//         loop {
//             if let Some(&Token::ParenClose) = self.tokens.peek() {
//                 self.tokens.next();
//                 break;
//             }
//             args.push(self.parse_primary()?);
//             match self.tokens.next() {
//                 Some(Token::Comma) => (),
//                 Some(Token::ParenClose) => break,
//                 Some(token) => return Err(ParseError::UnexpectedToken(token)),
//                 None => return Err(ParseError::UnexpectedEOF),
//             }
//         }
//         Ok(Expr::Call(Box::new(func), args))
//     }

//     fn parse_object(&mut self) -> Result<Expr, ParseError> {
//         let mut properties = HashMap::new();
//         loop {
//             match self.tokens.next() {
//                 Some(Token::Identifier(name)) => {
//                     if self.tokens.next() != Some(Token::Colon) {
//                         return Err(ParseError::UnexpectedToken(self.tokens.next().unwrap()));
//                     }
//                     let value = self.parse_primary()?;
//                     properties.insert(name, value);
//                 }
//                 Some(Token::CurlyBraceClose) => break,
//                 Some(token) => return Err(ParseError::UnexpectedToken(token)),
//                 None => return Err(ParseError::UnexpectedEOF),
//             }
//             match self.tokens.next() {
//                 Some(Token::Comma) => (),
//                 Some(Token::CurlyBraceClose) => break,
//                 Some(token) => return Err(ParseError::UnexpectedToken(token)),
//                 None => return Err(ParseError::UnexpectedEOF),
//             }
//         }
//         Ok(Expr::Object(properties))
//     }

//     fn parse_primary(&mut self) -> Result<Expr, ParseError> {
//         let mut expr = self.parse_primary()?;
//         loop {
//             match self.tokens.peek() {
//                 Some(&Token::ParenOpen) => {
//                     self.tokens.next();
//                     expr = self.parse_call(expr)?;
//                 }
//                 _ => break,
//             }
//         }
//         Ok(expr)
//     }

//     pub fn parse(&mut self) -> Result<Expr, ParseError> {
//         self.parse_primary()
//     }
// }

// #[test]
// fn test_parser() {
//     let input = "myResult: MyFunction(String(\"Value\")) {
//         callBack: {
//             io.print({String(\"Hello, world!\"), Int(123)})
//         },
//     }";

//     let expected = Expr::Object({
//         let mut ast = HashMap::new();
//         ast.insert(
//             "myResult".to_string(),
//             Expr::CallWithBody(
//                 Box::new(Expr::Ident("MyFunction".to_string())),
//                 vec![
//                     Expr::Call(
//                         Box::new(Expr::Ident("String".to_string())),
//                         vec![Expr::StringLit("Value".to_string())]),
//                 ],
//                 {
//                     let mut ast = HashMap::new();
//                     ast.insert(
//                         "callBack".to_string(),
//                         Expr::Object({
//                             let mut ast = HashMap::new();
//                             ast.insert(
//                                 "io.print".to_string(),
//                                 Expr::Call(
//                                     Box::new(Expr::Ident("io.print".to_string())),
//                                     vec![
//                                         Expr::Object({
//                                             let mut ast = HashMap::new();
//                                             ast.insert("String".to_string(), Expr::StringLit("Hello, world!".to_string()));
//                                             ast.insert("Int".to_string(), Expr::IntLit(123));
//                                             ast
//                                         })
//                                     ],
//                                 ),
//                             );
//                             ast
//                         })
//                     );
//                     ast
//                 },

//             ),
//         );
//         ast
//     });

//     let mut parser = Parser::new(input);
//     let result = parser.parse();

//     println!("{}", serde_json::to_string_pretty(&result).unwrap());
//     println!("{}", serde_json::to_string_pretty(&expected).unwrap());
//     assert_eq!(result, Ok(expected));
// }